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

    @api.constrains('name')
    def _check_year_format(self):
        for record in self:
            if len(record.name or '') != 4 or not record.name.isdigit():
                raise ValidationError('سنة الصنع يجب أن تتكون من أربعة أرقام.')
