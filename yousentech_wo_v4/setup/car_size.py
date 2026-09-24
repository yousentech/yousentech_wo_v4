# -*- coding: utf-8 -*-

from odoo import fields, models


class CarSize(models.Model):
    _name = 'wof.car.size'
    _inherit = ['wof.api.mixin', 'mail.thread']
    _description = 'حجم سيارة'
    _order = 'name'
    _check_company_auto = True

    code = fields.Char(string="الكود", required=True, index=True, copy=False)
    name = fields.Char(
        string="الاسم", required=True, index=True,
        translate=True, tracking=True,
    )
    active = fields.Boolean(string="تفعيل", default=True)
    company_id = fields.Many2one(
        'res.company', string="الشركة", required=True,
        default=lambda self: self.env.company, ondelete='cascade', index=True,
    )

    _sql_constraints = [
        ('car_size_name_company_unique', 'unique(name, company_id)',
         'حجم السيارة مضاف مسبقًا لنفس الشركة.'),
        ('car_size_code_company_unique', 'unique(code, company_id)',
         'كود حجم السيارة مستخدم مسبقًا لنفس الشركة.'),
    ]
