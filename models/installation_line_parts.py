# -*- coding: utf-8 -*-
"""Parts of a service area on an installation order.

A service area (منطقة خدمة) is priced as a whole, but its work happens part by
part: each part of the chosen template keeps its own colour grade, stock
product and quantity, technicians and progress. The service line shows a
summary and stays the unit for price, invoice and commission; its technicians
are the union of its parts' technicians and its progress the average.
"""

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError

SETUP_STATES = ('draft', 'scheduled', 'intake', 'in_progress')
PART_KEYS = {'grade_id', 'product_id', 'product_qty', 'technician_ids', 'progress'}


class WofInstallationOrderLinePart(models.Model):
    _name = 'wof.installation.order.line.part'
    _description = 'جزء من منطقة خدمة في أمر التركيب'
    _order = 'line_id, sequence, id'

    line_id = fields.Many2one('wof.installation.order.line', string='الخدمة', required=True,
                              ondelete='cascade', index=True)
    order_id = fields.Many2one(related='line_id.order_id', store=True, index=True, readonly=True)
    company_id = fields.Many2one(related='line_id.company_id', store=True, readonly=True)
    sequence = fields.Integer(default=10)
    part_id = fields.Many2one('wof.car.parts', string='الجزء', required=True, ondelete='restrict')
    grade_id = fields.Many2one('wof.film.category.lines', string='الدرجة', ondelete='restrict')
    product_id = fields.Many2one('product.product', string='الصنف المخزني', ondelete='restrict')
    product_qty = fields.Float(string='الكمية', default=1.0, digits='Product Unit of Measure')
    technician_ids = fields.Many2many('hr.employee', 'wof_order_line_part_technician_rel', 'part_line_id',
                                      'employee_id', string='الفنيون', copy=False)
    technician_names = fields.Char(string='أسماء الفنيين', compute='_compute_technician_names',
                                   store=True, compute_sudo=True)
    progress = fields.Integer(string='التقدم %', default=0)

    @api.depends('technician_ids.name')
    def _compute_technician_names(self):
        # From the relation itself: survives technicians moving to another branch.
        names = {}
        real = self.filtered('id')
        if real:
            self.flush_model(['technician_ids'])
            self.env['hr.employee'].flush_model(['name'])
            self.env.cr.execute("""
                SELECT rel.part_line_id, emp.name FROM wof_order_line_part_technician_rel rel
                JOIN hr_employee emp ON emp.id = rel.employee_id
                WHERE rel.part_line_id IN %s ORDER BY rel.part_line_id, emp.id
            """, (tuple(real.ids),))
            for part_id, name in self.env.cr.fetchall():
                names.setdefault(part_id, []).append(name)
        for part in self:
            found = names.get(part.id) if part.id else part.technician_ids.mapped('name')
            part.technician_names = '، '.join(n for n in (found or []) if n) or False

    @api.constrains('progress')
    def _check_progress(self):
        for part in self:
            if not 0 <= part.progress <= 100:
                raise ValidationError(_('تقدم الجزء بين 0 و100.'))

    # ---------------------------------------------------------------- rules
    def _wof_check_write(self, vals):
        if self.env.context.get('wof_part_internal'):
            return
        Line = self.env['wof.installation.order.line']
        for part in self:
            line = part.line_id
            state = line.order_id.state
            if {'grade_id', 'product_id', 'product_qty'} & set(vals):
                if not Line._wof_is_team_lead():
                    raise AccessError(_('تعديل درجة الجزء وصنفه متاح للاستقبال أو المشرف.'))
                if state not in SETUP_STATES:
                    raise ValidationError(_('لا يمكن تعديل أجزاء الخدمة بعد إرسال الأمر إلى فحص الجودة.'))
            if 'technician_ids' in vals:
                line._wof_check_team_write(vals['technician_ids'])
                final, added = Line._wof_team_ids_after(part.technician_ids.ids, vals['technician_ids'])
                if added:
                    line._wof_check_new_technicians({line: added}, {line: len(final)})
            if 'progress' in vals:
                Line._ensure_execution_editor(line.order_id)
                if state != 'in_progress':
                    raise ValidationError(_('تحديث تقدم الأجزاء متاح أثناء التنفيذ فقط.'))
                if not Line._wof_is_team_lead() and not (part.technician_ids & self.env.user.employee_ids):
                    raise AccessError(_('يمكن للفني تحديث الأجزاء المسندة إليه فقط.'))

    def write(self, vals):
        self._wof_check_write(vals)
        result = super().write(vals)
        if {'technician_ids', 'progress'} & set(vals):
            self.line_id._wof_sync_from_parts()
        return result

    @api.model_create_multi
    def create(self, vals_list):
        parts = super().create(vals_list)
        parts.line_id._wof_sync_from_parts()
        return parts


class WofInstallationOrderLineParts(models.Model):
    _inherit = 'wof.installation.order.line'

    part_line_ids = fields.One2many('wof.installation.order.line.part', 'line_id', string='أجزاء منطقة الخدمة')
    part_count = fields.Integer(string='عدد الأجزاء', compute='_compute_part_summary')
    part_missing_product = fields.Integer(string='أجزاء بلا صنف', compute='_compute_part_summary')
    part_grade_summary = fields.Char(string='ملخص الدرجات', compute='_compute_part_summary')

    @api.depends('part_line_ids.product_id', 'part_line_ids.grade_id', 'film_uses_inventory')
    def _compute_part_summary(self):
        for line in self:
            parts = line.part_line_ids
            line.part_count = len(parts)
            line.part_missing_product = len(parts.filtered(lambda p: not p.product_id)) \
                if line.film_uses_inventory else 0
            grades = parts.grade_id
            line.part_grade_summary = grades.display_name if len(grades) == 1 else (
                _('حسب الجزء') if grades else False)

    # -------------------------------------------------------------- building
    def _wof_build_parts(self):
        """(Re)build the parts from the chosen template with the service defaults."""
        Part = self.env['wof.installation.order.line.part'].with_context(wof_part_internal=True)
        for line in self.filtered(lambda rec: rec.part_kind == 'service_area'):
            line.part_line_ids.with_context(wof_part_internal=True).unlink()
            template = line.service_area_template_id or line.car_part_id.default_template_id
            product = line.film_product_id if line.film_uses_inventory else self.env['product.product']
            Part.create([{
                'line_id': line.id, 'sequence': index * 10, 'part_id': part.id,
                'grade_id': line.film_category_line_id.id, 'product_id': product.id, 'product_qty': 1.0,
            } for index, part in enumerate(template.component_ids, start=1)])
            line._wof_sync_from_parts()

    def _wof_sync_from_parts(self):
        """Service technicians = union of its parts' technicians; progress = average."""
        for line in self.filtered('part_line_ids'):
            parts = line.part_line_ids
            self.env['wof.installation.order.line.part'].flush_model(['technician_ids'])
            self.env.cr.execute("""
                SELECT DISTINCT employee_id FROM wof_order_line_part_technician_rel WHERE part_line_id IN %s
            """, (tuple(parts.ids),))
            employee_ids = [row[0] for row in self.env.cr.fetchall()]
            progress = round(sum(parts.mapped('progress')) / len(parts))
            line.with_context(wof_skip_technician_check=True)._write_line_internal({
                'technician_ids': [(6, 0, employee_ids)], 'execution_progress': progress,
            })

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.filtered(lambda rec: rec.part_kind == 'service_area')._wof_build_parts()
        return lines

    def write(self, vals):
        if self.filtered('part_line_ids') and 'execution_progress' in vals \
                and not self.env.context.get('wof_order_line_internal_token'):
            raise ValidationError(_('تقدم منطقة الخدمة يُحسب من تقدم أجزائها.'))
        result = super().write(vals)
        if 'service_area_template_id' in vals or 'car_part_id' in vals:
            self._wof_build_parts()
        return result

    # ------------------------------------------------------------ stock needs
    def _wof_stock_needs(self):
        """[(product, qty)] this service takes from stock (per part for service areas)."""
        self.ensure_one()
        if not self.film_uses_inventory:
            return []
        if self.part_line_ids:
            return [(part.product_id, part.product_qty) for part in self.part_line_ids
                    if part.product_id and part.product_qty > 0]
        if self.film_product_id and self.film_product_qty > 0:
            return [(self.film_product_id, self.film_product_qty)]
        return []

    # ------------------------------------------------------------ widget API
    def wof_area_load(self):
        """Everything the service-area table needs in one call."""
        self.ensure_one()
        order = self.order_id
        lead = self._wof_is_team_lead()
        templates = self.car_part_id.template_ids.filtered('active').sorted(lambda rec: (rec.sequence, rec.id))
        return {
            'line_id': self.id,
            'template_id': (self.service_area_template_id or self.car_part_id.default_template_id).id,
            'templates': [{'id': t.id, 'name': t.name, 'is_default': t.is_default} for t in templates],
            'grades': [{'id': g.id, 'name': g.display_name} for g in self.available_grade_ids],
            'products': self._wof_stock_choices(),
            'technicians': [{'id': e.id, 'name': e.name} for e in self.available_technician_ids],
            'uses_inventory': bool(self.film_uses_inventory),
            'can_setup': lead and order.state in SETUP_STATES,
            'can_template': lead and order.state in ('draft', 'scheduled'),
            'can_team': order.state in SETUP_STATES and (
                lead or (self.env.user.has_group('yousentech_wo_v4.group_wo_technician')
                         and order.state in ('intake', 'in_progress'))),
            'can_progress': order.state == 'in_progress',
            'my_employee_ids': self.env.user.employee_ids.ids,
            'parts': [{
                'id': p.id, 'name': p.part_id.name, 'grade_id': p.grade_id.id, 'product_id': p.product_id.id,
                'product_qty': p.product_qty, 'technician_ids': p.technician_ids.ids,
                'technician_names': p.technician_names or '', 'progress': p.progress,
                'tint_warning': p.tint_warning or '',
            } for p in self.part_line_ids],
        }

    def wof_line_load(self):
        """Editable data of one service row (any service, area or single part)."""
        self.ensure_one()
        order = self.order_id
        lead = self._wof_is_team_lead()
        base = self.wof_area_load() if self.part_line_ids else {
            'line_id': self.id, 'templates': [], 'parts': [],
            'grades': [{'id': g.id, 'name': g.display_name} for g in self.available_grade_ids],
            'products': self._wof_stock_choices(),
            'technicians': [{'id': e.id, 'name': e.name} for e in self.available_technician_ids],
            'uses_inventory': bool(self.film_uses_inventory),
            'can_setup': lead and order.state in SETUP_STATES,
            'can_template': False,
            'can_team': order.state in SETUP_STATES and (
                lead or (self.env.user.has_group('yousentech_wo_v4.group_wo_technician')
                         and order.state in ('intake', 'in_progress'))),
            'can_progress': order.state == 'in_progress',
            'my_employee_ids': self.env.user.employee_ids.ids,
        }
        base.update({
            'area': bool(self.part_line_ids),
            'grade_id': self.film_category_line_id.id,
            'product_id': self.film_product_id.id,
            'product_qty': self.film_product_qty,
            'technician_ids': self.technician_ids.ids,
            'technician_names': self.technician_names or '',
            'progress': self.execution_progress,
            'discount': {
                'allowed': self.discount_scope == 'service' and order.state in ('draft', 'scheduled') and lead,
                'shown': self.discount_scope == 'service',
                'type': self.discount_type, 'value': self.discount_value,
                'max_percent': self.max_discount_percent, 'amount': self.discount_amount,
            },
            'can_commercial': lead and order.state in ('draft', 'scheduled'),
            'tint_warning': self.tint_warning if self.has_tint_warning else '',
            'options': {
                'available': [{'id': o.id, 'name': o.name} for o in self.available_option_ids.filtered('active')],
                'selected': self.option_ids.ids,
                'required': bool(self.options_required),
                'can_edit': lead and order.state in ('draft', 'scheduled', 'intake'),
            },
        })
        return base

    def _wof_stock_choices(self):
        """Stock products offered for this service: the film's stock products, its
        grades' products and the ones already chosen; when the film defines none,
        the storable products of the company (so the list is never empty)."""
        film = self.film_category_id
        defined = film.stock_product_ids | film.default_product_id | film.film_category_line_ids.product_id
        products = (self.part_line_ids.product_id | self.film_product_id | defined).filtered('active')
        if not defined:
            products |= self.env['product.product'].search(
                [('type', '=', 'product'), ('company_id', 'in', [self.company_id.id, False])], limit=200, order='name')
        return [{'id': p.id, 'name': p.display_name} for p in products]

    def wof_line_update(self, vals):
        """Change one service row from the order screen (normal write: every rule applies)."""
        self.ensure_one()
        allowed = {'film_category_line_id', 'film_product_id', 'film_product_qty', 'technician_ids',
                   'discount_type', 'discount_value', 'execution_progress', 'option_ids'}
        vals = {key: value for key, value in (vals or {}).items() if key in allowed}
        if self.part_line_ids and {'technician_ids', 'execution_progress', 'film_product_id', 'film_product_qty'} & set(vals):
            raise ValidationError(_('فنيو منطقة الخدمة وتقدمها وأصنافها تُحدَّد لكل جزء.'))
        for key in ('film_category_line_id', 'film_product_id'):
            if key in vals:
                vals[key] = int(vals[key] or 0) or False
        if 'discount_value' in vals:
            # An emptied box means no discount.
            vals['discount_value'] = float(vals['discount_value'] or 0.0)
        if 'option_ids' in vals:
            vals['option_ids'] = [(6, 0, [int(i) for i in vals['option_ids'] or []])]
        if vals.get('film_category_line_id') and 'film_product_id' not in vals and self.film_uses_inventory:
            grade = self.env['wof.film.category.lines'].browse(int(vals['film_category_line_id']))
            if grade.product_id:
                vals['film_product_id'] = grade.product_id.id
        if 'technician_ids' in vals:
            ids = [int(i) for i in vals['technician_ids'] or []]
            current = set(self.technician_ids.ids)
            commands = [(4, i) for i in ids if i not in current] + [(3, i) for i in current if i not in ids]
            vals['technician_ids'] = commands
            if not commands:
                vals.pop('technician_ids')
        if vals:
            self.write(vals)
        return self.wof_line_load()

    def wof_area_set_template(self, template_id):
        self.ensure_one()
        if self.order_id.state not in ('draft', 'scheduled') or not self._wof_is_team_lead():
            raise ValidationError(_('تغيير نموذج منطقة الخدمة متاح قبل إكمال الاستلام للاستقبال أو المشرف.'))
        template = self.car_part_id.template_ids.filtered(lambda rec: rec.id == int(template_id or 0))
        if not template:
            raise ValidationError(_('النموذج غير متاح لهذه المنطقة.'))
        self._write_line_internal({'service_area_template_id': template.id})
        return self.wof_line_load()

    def wof_area_update(self, part_ids, vals):
        """Update one or several parts (several = «تطبيق على كل الأجزاء»)."""
        self.ensure_one()
        vals = {key: value for key, value in (vals or {}).items() if key in PART_KEYS}
        parts = self.part_line_ids.filtered(lambda rec: rec.id in (part_ids or []))
        if not parts or not vals:
            return self.wof_line_load()
        for key in ('grade_id', 'product_id'):
            if key in vals:
                vals[key] = int(vals[key] or 0) or False
        if vals.get('grade_id') and 'product_id' not in vals and self.film_uses_inventory:
            grade = self.env['wof.film.category.lines'].browse(vals['grade_id'])
            if grade.product_id:
                vals['product_id'] = grade.product_id.id
        if 'technician_ids' in vals:
            ids = [int(i) for i in vals['technician_ids'] or []]
            for part in parts:
                current = set(part.technician_ids.ids)
                commands = [(4, i) for i in ids if i not in current] + [(3, i) for i in current if i not in ids]
                if commands:
                    part.write({'technician_ids': commands})
            vals.pop('technician_ids')
        if vals:
            parts.write(vals)
        return self.wof_line_load()
