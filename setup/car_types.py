# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class CarType(models.Model):
    _name = 'wof.car.type'
    _description = 'Car Type'
    _order = 'manufactory_id,name'

    name = fields.Char(
        string="الاسم",
        required=True,
        index=True,
        translate=True,   # 👈 مهم لو عندك لغات
        tracking=True     # 👈 لو تستخدم chatter
    )
    
    manufactory_id = fields.Many2one('wof.car.manufactory',string="الشركة المصنعة", ondelete='cascade')

    active = fields.Boolean(
        string="تفعيل",
        default=True
    )

    _sql_constraints = [
        (
            "car_type_unique",
            "UNIQUE(name,manufactory_id)",   
            "نوع السيارة مضاف مسبقاً"
        ),
         
    ]
 

class CarManufactory(models.Model):
    _name = 'wof.car.manufactory'
    _description = 'Car Type'
    _order = 'name'

    name = fields.Char(
        string="الاسم",
        required=True,
        index=True,
        translate=True,   # 👈 مهم لو عندك لغات
        tracking=True     # 👈 لو تستخدم chatter
    )

    _sql_constraints = [
        (
            "manufactory_unique",
            "UNIQUE(name)",   
            "الشركة المصنعة مضاف مسبقاً"
        ),
         
    ]