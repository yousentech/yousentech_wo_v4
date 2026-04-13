# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ServiceType(models.Model):
    _name = 'wo.services.types'
    _description = 'Service Types'
    _rec_name = 'name'
    _order = 'name'

    name = fields.Char(
        string="الاسم",
        required=True,
        index=True,
        translate=True,   # 👈 مهم لو عندك لغات
        tracking=True     # 👈 لو تستخدم chatter
    )

    code = fields.Char(
        string="الكود",
        index=True,
        copy=False
    )

    company_id = fields.Many2one(
        'res.company',
        string="الشركة",
        default=lambda self: self.env.company,
        required=True,
        index=True
    )

    active = fields.Boolean(
        string="تفعيل",
        default=True
    )

    _sql_constraints = [
        (
            "service_kind_unique",
            "UNIQUE(name, company_id)",  # 👈 مهم جداً multi-company
            "نوع الخدمة مضاف مسبقاً لنفس الشركة"
        ),
        (
            "service_code_unique",
            "UNIQUE(code, company_id)",
            "الكود مستخدم مسبقاً"
        ),
    ]

    def name_get(self):
        result = []
        for rec in self:
            name = f"[{rec.code}] {rec.name}" if rec.code else rec.name
            result.append((rec.id, name))
        return result

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        args = args or []
        domain = []

        if name:
            domain = ['|', ('name', operator, name), ('code', operator, name)]

        records = self.search(domain + args, limit=limit)
        return records.name_get()