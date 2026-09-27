# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class WofServiceAreaTemplate(models.Model):
    _name = 'wof.service.area.template'
    _description = 'نموذج مكونات منطقة الخدمة'
    _order = 'sequence, id'
    _check_company_auto = True

    name = fields.Char(string='اسم النموذج', required=True, translate=True)
    sequence = fields.Integer(string='الترتيب', default=10)
    service_area_id = fields.Many2one(
        'wof.car.parts', string='منطقة الخدمة', required=True,
        ondelete='cascade', index=True, check_company=True,
        domain="[('part_type', '=', 'service_area')]",
    )
    company_id = fields.Many2one(
        'res.company', related='service_area_id.company_id', store=True,
        readonly=True, index=True,
    )
    component_ids = fields.Many2many(
        'wof.car.parts', 'wof_service_area_template_part_rel',
        'template_id', 'part_id', string='مكونات النموذج', required=True,
        domain="[('company_id', '=', company_id), ('part_type', '=', 'car_part'), ('active', '=', True)]",
    )
    is_default = fields.Boolean(string='النموذج الافتراضي', default=False, index=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('service_area_template_name_unique', 'unique(service_area_id, name)',
         'اسم النموذج مستخدم مسبقًا داخل منطقة الخدمة.'),
    ]

    @api.constrains('service_area_id', 'component_ids', 'company_id')
    def _check_template_components(self):
        for record in self:
            if record.service_area_id.part_type != 'service_area':
                raise ValidationError(_('يمكن إنشاء النماذج لمناطق الخدمة فقط.'))
            if not record.component_ids:
                raise ValidationError(_('يجب أن يحتوي نموذج منطقة الخدمة على مكوّن واحد على الأقل.'))
            wrong_type = record.component_ids.filtered(lambda part: part.part_type != 'car_part')
            if wrong_type:
                raise ValidationError(_('نموذج منطقة الخدمة يقبل مكونات من نوع جزء سيارة فقط.'))
            wrong_company = record.component_ids.filtered(lambda part: part.company_id != record.company_id)
            if wrong_company:
                raise ValidationError(_('جميع مكونات النموذج يجب أن تتبع نفس الشركة.'))

    @api.constrains('is_default', 'service_area_id', 'active')
    def _check_single_default(self):
        for record in self.filtered(lambda rec: rec.is_default and rec.active and rec.service_area_id):
            duplicate = self.search_count([
                ('id', '!=', record.id),
                ('service_area_id', '=', record.service_area_id.id),
                ('is_default', '=', True),
                ('active', '=', True),
            ])
            if duplicate:
                raise ValidationError(_('يمكن تحديد نموذج افتراضي واحد فقط لكل منطقة خدمة.'))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            siblings = record.service_area_id.template_ids.filtered('active')
            if len(siblings) == 1 and not record.is_default:
                record.with_context(skip_default_sync=True).is_default = True
            elif record.is_default:
                (siblings - record).with_context(skip_default_sync=True).write({'is_default': False})
        return records

    def write(self, vals):
        result = super().write(vals)
        if self.env.context.get('skip_default_sync'):
            return result
        if vals.get('is_default'):
            for record in self:
                record.service_area_id.template_ids.filtered(
                    lambda template: template.active and template != record and template.is_default
                ).with_context(skip_default_sync=True).write({'is_default': False})
        for area in self.mapped('service_area_id'):
            active_templates = area.template_ids.filtered('active')
            if len(active_templates) == 1 and not active_templates.is_default:
                active_templates.with_context(skip_default_sync=True).write({'is_default': True})
        return result

    def unlink(self):
        areas = self.mapped('service_area_id')
        result = super().unlink()
        for area in areas:
            active_templates = area.template_ids.filtered('active')
            if active_templates and not active_templates.filtered('is_default'):
                active_templates.sorted(lambda rec: (rec.sequence, rec.id))[:1].with_context(
                    skip_default_sync=True
                ).write({'is_default': True})
        return result
