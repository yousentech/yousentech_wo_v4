# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class CarManufactoryYear(models.Model):
    _name = 'wof.car.manufactory.year'
    _description = 'Car manufactory year'
    _order = 'name'

    name = fields.Char(
        string="الاسم",
        required=True,
      
    )
    active = fields.Boolean(
        string="تفعيل",
        default=True
    )

    _sql_constraints = [
        (
            "car_size_unique",
            "UNIQUE(name)",  # 👈 مهم جداً multi-company
            "ٍسنة الصنع للسيارة مضاف مسبقاً "
        ),
         
    ]
 