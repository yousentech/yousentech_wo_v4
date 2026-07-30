# -*- coding: utf-8 -*-

from odoo import fields, models


class CarPartOption(models.Model):
    _name = 'wof.car.part.options'
    _inherit = ['wof.api.mixin']
    _description = 'خيار إضافي لجزء السيارة'
    _order = 'name'

    code = fields.Char(string="الكود", required=True, index=True, copy=False)
    name = fields.Char(
        string="الاسم", required=True, index=True, translate=True,
    )
    active = fields.Boolean(string="تفعيل", default=True)

    _sql_constraints = [
        ('car_part_option_code_unique', 'unique(code)',
         'كود الخيار الإضافي مستخدم مسبقًا.'),
        ('car_part_option_name_unique', 'unique(name)',
         'اسم الخيار الإضافي مستخدم مسبقًا.'),
    ]


class PartsTransparencyLevel(models.Model):
    _name = 'wof.parts.transparency.level'
    _inherit = ['wof.api.mixin']
    _description = 'درجة شفافية الفيلم'
    _order = 'name'

    code = fields.Char(string="الكود", required=True, index=True, copy=False)
    name = fields.Char(
        string="الاسم", required=True, index=True, translate=True,
    )
    active = fields.Boolean(string="تفعيل", default=True)

    _sql_constraints = [
        ('transparency_level_code_unique', 'unique(code)',
         'كود درجة الشفافية مستخدم مسبقًا.'),
        ('transparency_level_name_unique', 'unique(name)',
         'اسم درجة الشفافية مستخدم مسبقًا.'),
    ]
