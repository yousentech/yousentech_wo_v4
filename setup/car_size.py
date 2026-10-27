# -*- coding: utf-8 -*-

from odoo import fields, models


class CarSize(models.Model):
    _name = 'wof.car.size'
    _inherit = ['wof.api.mixin', 'mail.thread']
    _description = 'حجم سيارة'
    _order = 'name'

    code = fields.Char(string="الكود", required=True, index=True, copy=False)
    name = fields.Char(
        string="الاسم", required=True, index=True,
        translate=True, tracking=True,
    )
    active = fields.Boolean(string="تفعيل", default=True)

    _sql_constraints = [
        ('car_size_name_company_unique', 'unique(name)',
         'حجم السيارة مضاف مسبقًا.'),
        ('car_size_code_company_unique', 'unique(code)',
         'كود حجم السيارة مستخدم مسبقًا.'),
    ]
