# -*- coding: utf-8 -*-
"""'Add service' picker of the installation order: activity -> film -> component.

The picker only reads the ready catalog (active films and their selected
components, priced for the order's car size) and then creates order lines the
normal way, so every existing rule on lines (pricing, grades, stock product,
discount limits, locks) still applies. A service area keeps the template
(النموذج) chosen for it; its default template is used when none is chosen.
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class WofInstallationOrderLineTemplate(models.Model):
    _inherit = 'wof.installation.order.line'

    service_area_template_id = fields.Many2one(
        'wof.service.area.template', string='نموذج منطقة الخدمة', ondelete='restrict',
        domain="[('service_area_id', '=', car_part_id), ('active', '=', True)]",
        help='يحدد أجزاء منطقة الخدمة التي تُنفّذ في هذا السطر.',
    )
    template_part_names = fields.Char(string='أجزاء النموذج', compute='_compute_template_part_names')

    @api.depends('service_area_template_id', 'car_part_id')
    def _compute_template_part_names(self):
        for line in self:
            template = line.service_area_template_id or (
                line.car_part_id.default_template_id if line.car_part_id.part_type == 'service_area' else False)
            line.template_part_names = '، '.join(template.component_ids.mapped('name')) if template else False

    @api.onchange('car_part_id')
    def _onchange_wof_default_template(self):
        part = self.car_part_id
        self.service_area_template_id = part.default_template_id if part.part_type == 'service_area' else False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('car_part_id') and not vals.get('service_area_template_id'):
                part = self.env['wof.car.parts'].browse(vals['car_part_id'])
                if part.part_type == 'service_area' and part.default_template_id:
                    vals['service_area_template_id'] = part.default_template_id.id
        return super().create(vals_list)


class WofInstallationOrderCatalog(models.Model):
    _inherit = 'wof.installation.order'

    def _wof_catalog_price(self, part_line):
        Price = self.env['wof.film.parts.price.lines']
        price = Price.search([('part_line_id', '=', part_line.id), ('car_size_id', '=', self.car_size_id.id)], limit=1) \
            or Price.search([('part_line_id', '=', part_line.id), ('car_size_id', '=', False)], limit=1)
        if not price:
            return None
        return 0.0 if price.free_part else price.part_price

    def wof_service_catalog(self):
        """Activities -> ready films -> components with this order's price."""
        self.ensure_one()
        Film = self.env['wof.film.category']
        activities = self.env['wof.service.type'].search([('active', '=', True)], order='id').sorted(Film._wof_activity_rank)
        films = Film.search([('service_type_id', 'in', activities.ids), ('active', '=', True)], order='sequence, name')
        existing = {(line.film_category_id.id, line.car_part_id.id) for line in self.line_ids}
        result = []
        for activity in activities:
            items = []
            for film in films.filtered(lambda rec: rec.service_type_id == activity):
                comps = []
                for part_line in film.film_part_line_ids.filtered('part_selected').sorted(lambda rec: (rec.sequence, rec.id)):
                    part = part_line.car_part_id
                    if not part.active:
                        continue
                    templates = part.template_ids.filtered('active').sorted(lambda rec: (rec.sequence, rec.id)) \
                        if part.part_type == 'service_area' else self.env['wof.service.area.template']
                    comps.append({
                        'id': part.id, 'name': part.name, 'area': part.part_type == 'service_area',
                        'price': self._wof_catalog_price(part_line),
                        'added': (film.id, part.id) in existing,
                        'default_template': part.default_template_id.id if templates else False,
                        'templates': [{
                            'id': tpl.id, 'name': tpl.name, 'is_default': tpl == part.default_template_id,
                            'parts': tpl.component_ids.mapped('name'),
                        } for tpl in templates],
                    })
                if comps:
                    priced = [c['price'] for c in comps if c['price'] is not None]
                    items.append({
                        'id': film.id, 'name': film.name, 'code': film.code or '',
                        'description': film.description or '',
                        'from': min(priced) if priced else None, 'comps': comps,
                    })
            if items:
                result.append({'id': activity.id, 'name': activity.name,
                               'type': activity.service_options or 'others', 'films': items})
        currency = self.currency_id or self.env.company.currency_id
        return {
            'order': {'id': self.id, 'name': self.name, 'size': self.car_size_id.name or ''},
            'currency': currency.symbol or currency.name or '',
            'activities': result,
        }

    def wof_add_services(self, items):
        """Create one order line per chosen component (normal create, all rules apply)."""
        self.ensure_one()
        if self.state not in ('draft', 'scheduled'):
            raise ValidationError(_('لا يمكن إضافة خدمات بعد إكمال استلام السيارة.'))
        if not items:
            raise ValidationError(_('اختر مكوّنًا واحدًا على الأقل.'))
        Line = self.env['wof.installation.order.line']
        vals_list = []
        for item in items:
            film = self.env['wof.film.category'].browse(int(item.get('film_id') or 0)).exists()
            part = self.env['wof.car.parts'].browse(int(item.get('part_id') or 0)).exists()
            if not film or not part:
                raise ValidationError(_('الخدمة المختارة غير متاحة.'))
            vals = {
                'order_id': self.id, 'service_type_id': film.service_type_id.id,
                'film_category_id': film.id, 'car_part_id': part.id,
            }
            template_id = int(item.get('template_id') or 0)
            if template_id and template_id in part.template_ids.ids:
                vals['service_area_template_id'] = template_id
            vals_list.append(vals)
        Line.create(vals_list)
        return True

    def action_open_add_services(self):
        self.ensure_one()
        if self.state not in ('draft', 'scheduled'):
            raise ValidationError(_('لا يمكن إضافة خدمات بعد إكمال استلام السيارة.'))
        if not self.car_size_id:
            raise ValidationError(_('حدد حجم السيارة أولًا ليظهر السعر الصحيح.'))
        return {
            'type': 'ir.actions.client', 'tag': 'wof_order_add_services', 'name': _('إضافة خدمة'),
            'target': 'new', 'params': {'order_id': self.id},
            'context': {'dialog_size': 'extra-large'},
        }
