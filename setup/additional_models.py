# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class xx_parts_additional_options(models.Model):
    _name = 'wof.car.part.options'
    _description = 'Car agency'
    _order = 'name'
    _rec_name = 'name'
   
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
            "part_options_unique",
            "UNIQUE(name)",  # 👈 مهم جداً multi-company
            "الاسم مضاف مسبقاً"
        )]

class xx_parts_transparency_level(models.Model):
    _name = 'wof.parts.transparency.level'
    _description = 'parts transparency level'
    _order = 'name'
    _rec_name = 'name'
   
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
            "part_options_unique",
            "UNIQUE(name)",  # 👈 مهم جداً multi-company
            "الاسم مضاف مسبقاً"
        )]