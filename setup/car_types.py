# -*- coding: utf-8 -*-

from odoo import fields, models


class CarManufactory(models.Model):
    _name = 'wof.car.manufactory'
    _inherit = ['wof.api.mixin']
    _description = 'الشركة المصنعة للسيارة'
    _order = 'name'

    code = fields.Char(string="الكود", required=True, index=True, copy=False)
    name = fields.Char(
        string="الاسم", required=True, index=True, translate=True,
    )
    active = fields.Boolean(string="تفعيل", default=True)

    _sql_constraints = [
        ('car_manufactory_code_unique', 'unique(code)',
         'كود الشركة المصنعة مستخدم مسبقًا.'),
        ('car_manufactory_name_unique', 'unique(name)',
         'الشركة المصنعة مضافة مسبقًا.'),
    ]


class CarType(models.Model):
    _name = 'wof.car.type'
    _inherit = ['wof.api.mixin']
    _description = 'طراز السيارة'
    _order = 'manufactory_id, name'

    code = fields.Char(string="الكود", required=True, index=True, copy=False)
    name = fields.Char(
        string="الاسم", required=True, index=True, translate=True,
    )
    manufactory_id = fields.Many2one(
        'wof.car.manufactory', string="الشركة المصنعة",
        required=True, ondelete='restrict', index=True,
    )
    active = fields.Boolean(string="تفعيل", default=True)

    _sql_constraints = [
        ('car_type_code_manufactory_unique',
         'unique(code, manufactory_id)',
         'كود طراز السيارة مستخدم مسبقًا لدى الشركة المصنعة.'),
        ('car_type_name_manufactory_unique',
         'unique(name, manufactory_id)',
         'طراز السيارة مضاف مسبقًا لدى الشركة المصنعة.'),
    ]
