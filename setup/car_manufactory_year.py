# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CarManufactoryYear(models.Model):
    _name = 'wof.car.manufactory.year'
    _inherit = ['wof.api.mixin']
    _description = 'سنة صنع السيارة'
    _order = 'name desc'

    code = fields.Char(string="الكود", required=True, index=True, copy=False)
    name = fields.Char(string="السنة", required=True, index=True)
    active = fields.Boolean(string="تفعيل", default=True)

    _sql_constraints = [
        ('car_manufactory_year_code_unique', 'unique(code)',
         'كود سنة الصنع مستخدم مسبقًا.'),
        ('car_manufactory_year_name_unique', 'unique(name)',
         'سنة صنع السيارة مضافة مسبقًا.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        # Typed from the order ("2025"): the year is its own code.
        for vals in vals_list:
            name = (vals.get('name') or '').strip()
            vals['name'] = name
            if not vals.get('code') and name:
                vals['code'] = name
        return super().create(vals_list)

    @api.model
    def name_create(self, name):
        name = (name or '').strip()
        if len(name) != 4 or not name.isdigit():
            raise ValidationError('اكتب سنة الصنع بأربعة أرقام، مثل 2025.')
        existing = self.with_context(active_test=False).search([('name', '=', name)], limit=1)
        if existing:
            if not existing.active:
                existing.active = True
            return existing.id, existing.display_name
        return super().name_create(name)

    @api.constrains('name')
    def _check_year_format(self):
        for record in self:
            if len(record.name or '') != 4 or not record.name.isdigit():
                raise ValidationError('سنة الصنع يجب أن تتكون من أربعة أرقام.')
