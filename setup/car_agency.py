# -*- coding: utf-8 -*-

from odoo import fields, models


class CarAgency(models.Model):
    _name = 'wof.car.agency'
    _inherit = ['wof.api.mixin']
    _description = 'وكالة السيارة'
    _order = 'name'

    code = fields.Char(string="الكود", required=True, index=True, copy=False)
    name = fields.Char(
        string="الاسم", required=True, index=True, translate=True,
    )
    active = fields.Boolean(string="تفعيل", default=True)

    _sql_constraints = [
        ('car_agency_code_unique', 'unique(code)',
         'كود وكالة السيارة مستخدم مسبقًا.'),
        ('car_agency_name_unique', 'unique(name)',
         'وكالة السيارة مضافة مسبقًا.'),
    ]
