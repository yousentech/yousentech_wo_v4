# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ServiceType(models.Model):
    _name = 'wof.service.type'
    _description = 'Service Types'
    _order = 'code, name'
    _company_auto = True   # 👈 هنا المكان الصحيح

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
    display_name = fields.Char(compute='_compute_display_name', store=True)

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for rec in self:
            if rec.code:
                rec.display_name = f"[{rec.code}] {rec.name}"
            else:
                rec.display_name = rec.name


    def _default_company_parent(self):
        company = self.env.company
        return company.parent_id or company

    company_id = fields.Many2one(
        'res.company',
        string="الشركة",
        default=_default_company_parent,
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
 
    # @api.model
    # def name_get(self):
    #     result = []
    #     for rec in self:
    #         name = rec.name
    #         display_name = ""
    #         new_name = ""
            
    #         if rec.code:
    #             service_code = "[" + rec.code +"]"
    #             new_name =  f"{service_code}   {name}"
    #         else:
    #             new_name =  name
    #         display_name = new_name
    #         result.append((rec.id, display_name))
    #     return result

    @api.model
    def name_get(self):
        result = []
        for rec in self:
            code = rec.code or ''
            name = rec.name or ''

            display_name = f"[{code}] {name}" if code else name
            result.append((rec.id, display_name))

        return result
     
    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        args = args or []
        domain = []
        if name:
            domain = [
                '|',
                ('name', operator, name),
                ('code', operator, name),
            ]
            domain += args
        else:
            domain = args
        
        services = self.search(domain, limit=limit)
        if services:
            return services.name_get()
        return super().name_search(name, args=args, operator=operator, limit=limit)
    





    @api.model
    def create(self, vals):
        company = self.env.company
        vals['company_id'] = company.parent_id.id if company.parent_id else company.id
        return super().create(vals)


    def write(self, vals):
        if 'company_id' in vals:
            company = self.env.company
            vals['company_id'] = company.parent_id.id if company.parent_id else company.id
        return super().write(vals)