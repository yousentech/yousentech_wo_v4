# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class CarِِِِAgency(models.Model):
    _name = 'wof.car.agency'
    _description = 'Car agency'
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
            "وكالة السيارة مضاف مسبقاً"
        ),
         
    ]
 