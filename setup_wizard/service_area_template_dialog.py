# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class WofFilmSetupComponentCreateDialog(models.TransientModel):
    _inherit = 'wof.film.setup.component.create.dialog'

    template_line_ids = fields.One2many(
        'wof.film.setup.service.area.template.line', 'dialog_id',
        string='نماذج مكونات منطقة الخدمة',
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records.filtered(lambda rec: rec.expected_type == 'service_area'):
            record._load_template_lines()
        return records

    def _load_template_lines(self):
        self.ensure_one()
        if self.template_line_ids:
            return
        part = self.edit_part_id
        if part:
            part.ensure_service_area_templates()
            templates = part.template_ids.filtered('active').sorted(lambda rec: (rec.sequence, rec.id))
            for template in templates:
                self.env['wof.film.setup.service.area.template.line'].create({
                    'dialog_id': self.id, 'template_id': template.id,
                    'name': template.name, 'sequence': template.sequence,
                    'is_default': template.is_default,
                    'component_ids': [(6, 0, template.component_ids.ids)],
                })
        if not self.template_line_ids:
            self.env['wof.film.setup.service.area.template.line'].create({
                'dialog_id': self.id, 'name': _('النموذج الأساسي'),
                'sequence': 10, 'is_default': True,
                'component_ids': [(6, 0, self.service_area_part_ids.ids)],
            })

    def _validate_template_lines(self):
        self.ensure_one()
        if self.expected_type != 'service_area':
            return
        lines = self.template_line_ids
        if not lines:
            raise ValidationError(_('أضف نموذج مكونات واحدًا على الأقل لمنطقة الخدمة.'))
        if lines.filtered(lambda line: not (line.name or '').strip()):
            raise ValidationError(_('أدخل اسمًا لكل نموذج مكونات.'))
        if lines.filtered(lambda line: not line.component_ids):
            raise ValidationError(_('كل نموذج يجب أن يحتوي على مكوّن واحد على الأقل.'))
        defaults = lines.filtered('is_default')
        if len(defaults) != 1:
            raise ValidationError(_('حدد نموذجًا افتراضيًا واحدًا فقط لمنطقة الخدمة.'))
        names = [(line.name or '').strip().lower() for line in lines]
        if len(names) != len(set(names)):
            raise ValidationError(_('لا يمكن تكرار اسم النموذج داخل منطقة الخدمة.'))
        wrong = lines.mapped('component_ids').filtered(
            lambda part: part.company_id != self.company_id or part.part_type != 'car_part'
        )
        if wrong:
            raise ValidationError(_('مكونات النماذج يجب أن تكون أجزاء سيارة من نفس الشركة.'))
        self.service_area_part_ids = [(6, 0, defaults.component_ids.ids)]

    def _sync_persistent_templates(self, part):
        self.ensure_one()
        if self.expected_type != 'service_area':
            return
        Template = self.env['wof.service.area.template'].with_context(active_test=False)
        keep_ids = []
        default_line = self.template_line_ids.filtered('is_default')[:1]
        for line in self.template_line_ids.sorted(lambda rec: (rec.sequence, rec.id)):
            vals = {
                'name': (line.name or '').strip(), 'sequence': line.sequence,
                'service_area_id': part.id,
                'component_ids': [(6, 0, line.component_ids.ids)],
                'active': True, 'is_default': line == default_line,
            }
            template = line.template_id
            if template and template.service_area_id == part:
                template.write(vals)
            else:
                template = Template.create(vals)
            keep_ids.append(template.id)
        obsolete = Template.search([
            ('service_area_id', '=', part.id), ('id', 'not in', keep_ids), ('active', '=', True),
        ])
        if obsolete:
            obsolete.write({'active': False, 'is_default': False})
        part.service_area_part_ids = [(6, 0, default_line.component_ids.ids)]

    def action_save_changes(self):
        self._validate_template_lines()
        part = self.edit_part_id
        result = super().action_save_changes()
        if part and self.expected_type == 'service_area':
            self._sync_persistent_templates(part)
        return result

    def action_create_and_add(self):
        self._validate_template_lines()
        result = super().action_create_and_add()
        if self.expected_type == 'service_area':
            part = self.env['wof.car.parts'].search([
                ('company_id', '=', self.company_id.id),
                ('name', '=ilike', (self.name or '').strip()),
                ('part_type', '=', 'service_area'),
            ], order='id desc', limit=1)
            if part:
                self._sync_persistent_templates(part)
        return result


class WofFilmSetupServiceAreaTemplateLine(models.TransientModel):
    _name = 'wof.film.setup.service.area.template.line'
    _description = 'نموذج مكونات منطقة خدمة داخل معالج الفيلم'
    _order = 'sequence, id'

    dialog_id = fields.Many2one('wof.film.setup.component.create.dialog', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='dialog_id.company_id', readonly=True)
    template_id = fields.Many2one('wof.service.area.template', readonly=True, ondelete='set null')
    sequence = fields.Integer(string='الترتيب', default=10)
    name = fields.Char(string='اسم النموذج', required=True)
    is_default = fields.Boolean(string='افتراضي')
    component_ids = fields.Many2many(
        'wof.car.parts', 'wof_film_setup_area_template_line_part_rel',
        'line_id', 'part_id', string='المكونات',
        domain="[('company_id', '=', company_id), ('part_type', '=', 'car_part'), ('active', '=', True)]",
    )

    @api.onchange('is_default')
    def _onchange_is_default(self):
        if self.is_default and self.dialog_id:
            for line in self.dialog_id.template_line_ids - self:
                line.is_default = False
