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
    
    service_options = fields.Selection([('tint','عزل حراري'),
                                        ('ppf','حماية'),
                                        ('nano','نانو سيراميك'),
                                        ('upholstery','تنجيد'),
                                        ('floor_mats'),
                                        ('others','أخرى')],string="النوع",default='tint',required=True)

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
    heat_insulation = fields.Boolean(string="النوع عزل حراري",  default=False )

    parts_count = fields.Integer(
    string="عدد الأجزاء", compute="_compute_counts"  )

    film_count = fields.Integer(
        string="عدد الأفلام",  compute="_compute_counts" )



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
 
    def _compute_counts(self):

        # ================= FILMS COUNT =================
        films_data = self.env['wof.film.category'].read_group(
            [('service_type_id', 'in', self.ids)],
            ['service_type_id'],
            ['service_type_id']
        )

        film_map = {
            item['service_type_id'][0]: item['service_type_id_count']
            for item in films_data
        }

        # ================= PARTS COUNT =================
        parts_data = self.env['wof.film.parts.lines'].read_group(
            [('service_type_id', 'in', self.ids)],
            ['service_type_id'],
            ['service_type_id']
        )

        part_map = {
            item['service_type_id'][0]: item['service_type_id_count']
            for item in parts_data
        }

        # ================= ASSIGN =================
        for rec in self:
            rec.film_count = film_map.get(rec.id, 0)
            rec.parts_count = part_map.get(rec.id, 0)
            

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
    
  
    # ================= SMART BUTTON =================
    def action_open_films(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': _('الأفلام'),
            'res_model': 'wof.film.category',
            'view_mode': 'kanban,tree,form',
            'domain': [('service_type_id', '=', self.id)],
            'context': {
                'default_service_type_id': self.id,
            }
        }
    def action_create_film(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': _('إضافة فيلم'),
            'res_model': 'wof.film.category',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_service_type_id': self.id,
            }
        } 
        
    def action_create_car_part(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': _('إضافة جزء الفيلم'),
            'res_model': 'wof.film.parts.lines',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_service_type_id': self.id,
            }
        }