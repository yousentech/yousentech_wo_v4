# -*- coding: utf-8 -*-
"""Customer vehicles with ownership history.

Like dealer systems, the vehicle is its own record (identified by VIN when
known, otherwise by its current plate) and keeps:

* the current owner and the history of every owner (with dates), so a car
  sold to another customer keeps its past orders for reports;
* changes of plate, specs and owner in its chatter.

Each installation order still stores the vehicle data it was made with (plate,
make, model, year, colour, VIN): when a plate later moves to another car, old
orders keep the car they were really about.
"""

import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

# Saudi plates: up to four digits and up to three letters from this set
# (Arabic letter, Latin letter shown on the plate).
SAUDI_PLATE_LETTERS = [
    ('ا', 'A'), ('ب', 'B'), ('ح', 'J'), ('د', 'D'), ('ر', 'R'), ('س', 'S'),
    ('ص', 'X'), ('ط', 'T'), ('ع', 'E'), ('ق', 'G'), ('ك', 'K'), ('ل', 'L'),
    ('م', 'Z'), ('ن', 'N'), ('هـ', 'H'), ('و', 'U'), ('ى', 'V'),
]
PLATE_COUNTRIES = [
    ('SA', 'السعودية'), ('AE', 'الإمارات'), ('KW', 'الكويت'), ('BH', 'البحرين'), ('QA', 'قطر'),
    ('OM', 'عُمان'), ('YE', 'اليمن'), ('JO', 'الأردن'), ('IQ', 'العراق'), ('EG', 'مصر'), ('OTHER', 'دولة أخرى'),
]
VEHICLE_SPEC_FIELDS = {
    # order field -> vehicle field
    'vehicle_plate_country': 'plate_country',
    'vehicle_vin': 'vin',
    'vehicle_manufacturer_id': 'manufacturer_id',
    'vehicle_model_id': 'model_id',
    'vehicle_year_id': 'year_id',
    'vehicle_color_id': 'color_id',
    'car_size_id': 'car_size_id',
    'agency_id': 'agency_id',
}


def normalize_plate(value):
    """Capital letters, single spaces: «abj  1234» -> «ABJ 1234»."""
    return re.sub(r'\s+', ' ', (value or '').strip().upper()) or False


class WofVehicle(models.Model):
    _name = 'wof.vehicle'
    _description = 'سيارة عميل'
    _inherit = ['mail.thread']
    _order = 'write_date desc, id desc'

    name = fields.Char(string='السيارة', compute='_compute_name', store=True)
    plate = fields.Char(string='رقم اللوحة', index=True, tracking=True)
    plate_country = fields.Selection(PLATE_COUNTRIES, string='دولة اللوحة', default='SA', required=True, tracking=True)
    vin = fields.Char(string='رقم الهيكل', index=True, tracking=True)
    partner_id = fields.Many2one(
        'res.partner', string='المالك الحالي', index=True, tracking=True, ondelete='restrict')
    manufacturer_id = fields.Many2one('wof.car.manufactory', string='الماركة', tracking=True, ondelete='restrict')
    model_id = fields.Many2one(
        'wof.car.type', string='الموديل', tracking=True, ondelete='restrict',
        domain="[('manufactory_id', '=', manufacturer_id)]")
    year_id = fields.Many2one('wof.car.manufactory.year', string='السنة', tracking=True, ondelete='restrict')
    color_id = fields.Many2one('wof.car.color', string='اللون', tracking=True, ondelete='restrict')
    car_size_id = fields.Many2one('wof.car.size', string='حجم السيارة', tracking=True, ondelete='restrict')
    agency_id = fields.Many2one('wof.car.agency', string='الوكالة', ondelete='restrict')
    owner_ids = fields.One2many('wof.vehicle.owner', 'vehicle_id', string='سجل الملاك')
    order_ids = fields.One2many('wof.installation.order', 'vehicle_id', string='أوامر التركيب')
    order_count = fields.Integer(string='الأوامر', compute='_compute_order_count')
    active = fields.Boolean(default=True)

    @api.depends('plate', 'manufacturer_id', 'model_id', 'year_id')
    def _compute_name(self):
        for vehicle in self:
            car = ' '.join(filter(None, [vehicle.manufacturer_id.name, vehicle.model_id.name, vehicle.year_id.name]))
            vehicle.name = ' · '.join(filter(None, [vehicle.plate, car])) or _('سيارة')

    def _compute_order_count(self):
        for vehicle in self:
            vehicle.order_count = len(vehicle.order_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'plate' in vals:
                vals['plate'] = normalize_plate(vals['plate'])
            if vals.get('vin'):
                vals['vin'] = vals['vin'].strip().upper()
        vehicles = super().create(vals_list)
        for vehicle in vehicles.filtered('partner_id'):
            self.env['wof.vehicle.owner'].create({
                'vehicle_id': vehicle.id, 'partner_id': vehicle.partner_id.id, 'date_start': fields.Date.today(),
            })
        return vehicles

    def write(self, vals):
        if 'plate' in vals:
            vals['plate'] = normalize_plate(vals['plate'])
        if vals.get('vin'):
            vals['vin'] = vals['vin'].strip().upper()
        if 'partner_id' in vals:
            partner = self.env['res.partner'].browse(vals['partner_id'])
            order = self.env['wof.installation.order'].browse(self.env.context.get('wof_owner_order_id') or [])
            for vehicle in self.filtered(lambda rec: rec.partner_id != partner):
                vehicle._wof_record_owner(partner, order)
        return super().write(vals)

    def _wof_record_owner(self, partner, order=None):
        """Close the current owner line and open one for ``partner``."""
        self.ensure_one()
        today = fields.Date.today()
        self.owner_ids.filtered(lambda line: not line.date_end).write({'date_end': today})
        if partner:
            self.env['wof.vehicle.owner'].create({
                'vehicle_id': self.id, 'partner_id': partner.id, 'date_start': today,
                'order_id': order.id if order else False,
            })

    def action_view_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('أوامر السيارة'),
            'res_model': 'wof.installation.order', 'view_mode': 'tree,form',
            'domain': [('vehicle_id', '=', self.id)],
        }


class WofVehicleOwner(models.Model):
    _name = 'wof.vehicle.owner'
    _description = 'مالك سيارة'
    _order = 'date_start desc, id desc'

    vehicle_id = fields.Many2one('wof.vehicle', string='السيارة', required=True, ondelete='cascade', index=True)
    partner_id = fields.Many2one('res.partner', string='المالك', required=True, ondelete='restrict', index=True)
    date_start = fields.Date(string='من', required=True, default=fields.Date.today)
    date_end = fields.Date(string='إلى')
    order_id = fields.Many2one('wof.installation.order', string='سُجّل من الأمر', ondelete='set null')
    is_current = fields.Boolean(string='الحالي', compute='_compute_is_current')

    def _compute_is_current(self):
        for line in self:
            line.is_current = not line.date_end


class ResPartnerVehicles(models.Model):
    _inherit = 'res.partner'

    wof_vehicle_ids = fields.One2many('wof.vehicle', 'partner_id', string='السيارات')


class WofInstallationOrderVehicle(models.Model):
    _inherit = 'wof.installation.order'

    vehicle_plate_country = fields.Selection(
        PLATE_COUNTRIES, string='دولة اللوحة', default='SA', required=True,
        help='اللوحات السعودية تُختار بالنقر؛ لوحات الدول الأخرى تُكتب كما هي.')
    vehicle_id = fields.Many2one(
        'wof.vehicle', string='سيارة العميل', index=True, ondelete='restrict', copy=False,
        domain="[('partner_id', '=', partner_id)]",
        help='اختر من سيارات العميل، أو اترك الحقل فارغًا واكتب بيانات السيارة فتُسجَّل له عند الحفظ.',
    )

    @api.onchange('partner_id')
    def _onchange_wof_vehicle_partner(self):
        if self.vehicle_id and self.vehicle_id.partner_id != self.partner_id:
            self.vehicle_id = False
        if not self.vehicle_id and self.partner_id and len(self.partner_id.wof_vehicle_ids) == 1:
            self.vehicle_id = self.partner_id.wof_vehicle_ids

    @api.onchange('vehicle_id')
    def _onchange_wof_vehicle(self):
        vehicle = self.vehicle_id
        if not vehicle:
            return
        self.vehicle_plate = vehicle.plate
        self.vehicle_plate_country = vehicle.plate_country
        for order_field, vehicle_field in VEHICLE_SPEC_FIELDS.items():
            if vehicle[vehicle_field]:
                self[order_field] = vehicle[vehicle_field]

    def _wof_sync_vehicle(self):
        """Link the order to the customer's vehicle record, creating it or
        moving its ownership when needed. The order keeps its own snapshot."""
        Vehicle = self.env['wof.vehicle']
        for order in self:
            plate = normalize_plate(order.vehicle_plate)
            if not plate or order.state == 'cancelled':
                continue
            specs = {vehicle_field: order[order_field].id if hasattr(order[order_field], 'id') else order[order_field]
                     for order_field, vehicle_field in VEHICLE_SPEC_FIELDS.items() if order[order_field]}
            vehicle = order.vehicle_id
            if not vehicle:
                vehicle = Vehicle.search([('plate', '=', plate), ('plate_country', '=', order.vehicle_plate_country)], limit=1)
                vin = specs.get('vin')
                if vehicle and vin and vehicle.vin and vehicle.vin != vin:
                    # Same plate, different car: the plate moved; the old car keeps its history.
                    vehicle.write({'plate': False})
                    vehicle = Vehicle
            if not vehicle:
                vehicle = Vehicle.create(dict(specs, plate=plate, partner_id=order.partner_id.id))
            else:
                changes = {key: value for key, value in specs.items()
                           if (vehicle[key].id if hasattr(vehicle[key], 'id') else vehicle[key]) != value}
                if vehicle.plate != plate:
                    changes['plate'] = plate
                if changes:
                    vehicle.write(changes)
                if order.partner_id and vehicle.partner_id != order.partner_id:
                    # Sold to another customer: ownership moves, history stays.
                    vehicle.with_context(wof_owner_order_id=order.id).write({'partner_id': order.partner_id.id})
            if order.vehicle_id != vehicle:
                order.with_context(wof_skip_vehicle_sync=True).write({'vehicle_id': vehicle.id})

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'vehicle_plate' in vals:
                vals['vehicle_plate'] = normalize_plate(vals['vehicle_plate'])
        orders = super().create(vals_list)
        orders._wof_sync_vehicle()
        for order in orders:
            if len(order.vehicle_id.order_ids) == 1:
                order.vehicle_id.owner_ids.filtered(lambda line: not line.order_id and not line.date_end).write({'order_id': order.id})
        return orders

    def write(self, vals):
        if 'vehicle_plate' in vals:
            vals['vehicle_plate'] = normalize_plate(vals['vehicle_plate'])
        result = super().write(vals)
        watched = {'vehicle_plate', 'partner_id', 'vehicle_id'} | set(VEHICLE_SPEC_FIELDS)
        if watched & set(vals) and not self.env.context.get('wof_skip_vehicle_sync'):
            self._wof_sync_vehicle()
        return result


VIN_RE = re.compile(r'^[A-HJ-NPR-Z0-9]{17}$')


class WofInstallationOrderVin(models.Model):
    _inherit = 'wof.installation.order'

    @api.constrains('vehicle_vin')
    def _check_vin(self):
        profile = self.env['wof.company.profile']._wof_get_profile()
        if profile and not profile.vin_validation:
            return
        for order in self.filtered('vehicle_vin'):
            if not VIN_RE.match(order.vehicle_vin):
                raise ValidationError(_(
                    'رقم الهيكل «%s» غير صحيح: يجب أن يكون 17 خانة من الأحرف الإنجليزية والأرقام بدون I وO وQ. '
                    'يمكن إيقاف هذا التحقق من الإعدادات للسيارات غير القياسية.') % order.vehicle_vin)


class ResPartnerMobileHistory(models.Model):
    _inherit = 'res.partner'

    # Changes from installation orders (or anywhere) appear in the customer's history with the user.
    mobile = fields.Char(tracking=True)
