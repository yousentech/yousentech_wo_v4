# -*- coding: utf-8 -*-
"""History of the installation order (the chatter below the order).

Order fields are tracked by Odoo. Changes inside the order — services added,
removed or changed (price, discount, grade, stock product, technicians…), parts
of a service area, accessories and extra materials — are written to the same
history as notes, with the old and new values and who made them.
"""

from markupsafe import Markup, escape

from odoo import api, fields, models, _

LINE_TRACKED = [
    'film_category_id', 'car_part_id', 'film_category_line_id', 'quantity', 'unit_price',
    'use_manual_price', 'manual_unit_price', 'price_override_reason', 'discount_type', 'discount_value',
    'film_product_id', 'film_product_qty', 'technician_ids', 'option_ids', 'execution_progress',
]
PART_TRACKED = ['grade_id', 'product_id', 'product_qty', 'technician_ids', 'progress']
EXTRA_TRACKED = ['product_id', 'quantity', 'price_unit', 'tax_ids']
MATERIAL_TRACKED = ['product_id', 'quantity']


def _value(record, name):
    field = record._fields[name]
    value = record[name]
    if field.type in ('many2one',):
        return value.display_name or '—'
    if field.type in ('many2many', 'one2many'):
        return '، '.join(value.mapped('display_name')) or '—'
    if field.type == 'selection':
        return dict(field._description_selection(record.env)).get(value) or '—'
    if field.type == 'boolean':
        return _('نعم') if value else _('لا')
    if field.type in ('float', 'monetary'):
        return ('%.2f' % value).rstrip('0').rstrip('.') if value else '0'
    return value or '—'


def _snapshot(records, names):
    return {rec.id: {name: _value(rec, name) for name in names if name in rec._fields} for rec in records}


def _post(order, title, rows=None):
    body = Markup('<b>%s</b>') % title
    if rows:
        body += Markup('<ul class="mb-0">%s</ul>') % Markup('').join(
            Markup('<li>%s: %s → <b>%s</b></li>') % (label, old, new) for label, old, new in rows)
    user = order.env.user
    # Users without an email still leave history (Odoo needs a sender address).
    sender = user.email_formatted or order.company_id.email_formatted or '"%s" <noreply@localhost>' % (user.name or 'Odoo')
    order.message_post(body=body, subtype_xmlid='mail.mt_note', author_id=user.partner_id.id, email_from=sender)


class _WofTrackedLines(models.AbstractModel):
    """Common history for records that belong to an order."""
    _name = 'wof.tracked.order.child'
    _description = 'سجل تغييرات بنود أمر التركيب'
    _wof_tracked = []

    def _wof_order(self):
        return self.order_id

    def _wof_label(self):
        return self.display_name

    def _wof_kind(self):
        return _('بند')

    def _wof_track_on(self):
        return not self.env.context.get('wof_no_track') and not self.env.context.get('install_mode')

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self._wof_track_on():
            for rec in records:
                order = rec._wof_order()
                if order:
                    _post(order, _('أُضيف %s: %s') % (rec._wof_kind(), rec._wof_label()))
        return records

    def write(self, vals):
        names = [name for name in self._wof_tracked if name in vals]
        if not names or not self._wof_track_on():
            return super().write(vals)
        before = _snapshot(self, names)
        result = super().write(vals)
        after = _snapshot(self, names)
        for rec in self:
            rows = [(rec._fields[name].string, before[rec.id][name], after[rec.id][name])
                    for name in names if before[rec.id][name] != after[rec.id][name]]
            if rows and rec._wof_order():
                _post(rec._wof_order(), _('تعديل %s: %s') % (rec._wof_kind(), rec._wof_label()), rows)
        return result

    def unlink(self):
        if self._wof_track_on():
            for rec in self:
                if rec._wof_order():
                    _post(rec._wof_order(), _('حُذف %s: %s') % (rec._wof_kind(), rec._wof_label()))
        return super().unlink()


class WofOrderLineTracking(models.Model):
    _name = 'wof.installation.order.line'
    _inherit = ['wof.installation.order.line', 'wof.tracked.order.child']
    _wof_tracked = LINE_TRACKED

    def _wof_label(self):
        return ' · '.join(filter(None, [self.car_part_id.name, self.film_category_id.name])) or self.display_name

    def _wof_kind(self):
        return _('خدمة')

    def _wof_track_on(self):
        # Values the system fills itself (suggested product, computed price…) are not history.
        return super()._wof_track_on() and not self.env.context.get('wof_order_line_internal_token')


class WofOrderLinePartTracking(models.Model):
    _name = 'wof.installation.order.line.part'
    _inherit = ['wof.installation.order.line.part', 'wof.tracked.order.child']
    _wof_tracked = PART_TRACKED

    def _wof_order(self):
        return self.line_id.order_id

    def _wof_label(self):
        return '%s / %s' % (self.line_id.car_part_id.name or '', self.part_id.name or '')

    def _wof_kind(self):
        return _('جزء')

    def _wof_track_on(self):
        # Parts are built with their service: only later changes are history.
        return super()._wof_track_on() and not self.env.context.get('wof_part_internal')

    @api.model_create_multi
    def create(self, vals_list):
        return super(WofOrderLinePartTracking, self.with_context(wof_no_track=True)).create(vals_list)

    def unlink(self):
        return super(WofOrderLinePartTracking, self.with_context(wof_no_track=True)).unlink()


class WofExtraLineTracking(models.Model):
    _name = 'wof.installation.extra.line'
    _inherit = ['wof.installation.extra.line', 'wof.tracked.order.child']
    _wof_tracked = EXTRA_TRACKED

    def _wof_label(self):
        return '%s × %s' % (self.product_id.display_name or '', _value(self, 'quantity'))

    def _wof_kind(self):
        return _('ملحق')


class WofMaterialLineTracking(models.Model):
    _name = 'wof.installation.material.line'
    _inherit = ['wof.installation.material.line', 'wof.tracked.order.child']
    _wof_tracked = MATERIAL_TRACKED

    def _wof_label(self):
        return '%s × %s' % (self.product_id.display_name or '', _value(self, 'quantity'))

    def _wof_kind(self):
        return _('مادة إضافية')


class WofOrderTrackedFields(models.Model):
    _inherit = 'wof.installation.order'
    # Technicians read the order and update their work: they may add to its history.
    _mail_post_access = 'read'

    @api.model_create_multi
    def create(self, vals_list):
        # Services created with a new order are part of its creation, not changes.
        orders = super(WofOrderTrackedFields, self.with_context(wof_no_track=True)).create(vals_list)
        return orders.with_env(self.env)

    company_id = fields.Many2one(tracking=True)
    vehicle_vin = fields.Char(tracking=True)
    vehicle_manufacturer_id = fields.Many2one(tracking=True)
    vehicle_model_id = fields.Many2one(tracking=True)
    vehicle_year_id = fields.Many2one(tracking=True)
    vehicle_color_id = fields.Many2one(tracking=True)
    car_size_id = fields.Many2one(tracking=True)
    supervisor_id = fields.Many2one(tracking=True)
    salesperson_id = fields.Many2one(tracking=True)
    order_discount_percent = fields.Float(tracking=True)
    customer_notes = fields.Text(tracking=True)
    cancellation_reason = fields.Text(tracking=True)
    picking_type_id = fields.Many2one(tracking=True)
    stock_location_id = fields.Many2one(tracking=True)
