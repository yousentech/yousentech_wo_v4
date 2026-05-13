# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class CarSize(models.Model):
    _name = 'wof.car.size'
    _description = 'Car Size'
    _order = 'name'

    name = fields.Char(
        string="الاسم",
        required=True,
        index=True,
        translate=True,   # 👈 مهم لو عندك لغات
        tracking=True     # 👈 لو تستخدم chatter
    )
    active = fields.Boolean(
        string="تفعيل",
        default=True
    )

    _sql_constraints = [
        (
            "car_size_unique",
            "UNIQUE(name)",  # 👈 مهم جداً multi-company
            "حجم السيارة مضاف مسبقاً لنفس الشركة"
        ),
         
    ]
 