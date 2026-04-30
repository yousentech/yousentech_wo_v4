# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.osv import expression


class CarِِِِParts(models.Model):
    _name = 'wof.car.parts'
    _description = 'Car Part'
    _order = 'name'
 
    
    name = fields.Char(
        string="الاسم",
        required=True,
        index=True,
        translate=True,   # 👈 مهم لو عندك لغات
        tracking=True     # 👈 لو تستخدم chatter
    )

    service_type_id = fields.Many2one('wof.service.type', string="نوع الخدمة",required=True, index=True)
 
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
    
    commission = fields.Float(string="عمولة الفني")
    default_qty = fields.Float(string="المقاس الافتراضي للجزء",)
    
    part_lines = fields.One2many('wof.car.parts.lines','header_id',required=True, ondelete="cascade")
    part_com_lines = fields.One2many('wof.car.parts.com.lines','header_id',required=True, ondelete="cascade")
    part_sizes_lines = fields.One2many('wof.car.parts.size.lines','header_id',required=True, ondelete="cascade")
 
    active = fields.Boolean(
        string="تفعيل",
        default=True
    )
    _sql_constraints = [
        ("car_part_unique",
         "UNIQUE(name)",
         "تنبيه .. جزء السيارة تم اضافتة مسبقا لا يمكن الاستمرار"),
    ]

   
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
 
class xx_car_parts_lines(models.Model):
    _name = 'wof.car.parts.lines'
    _rec_name = 'name'
    
    name = fields.Char(string="الاسم",required=True)
    
    header_id = fields.Many2one('wof.car.parts',required=True,ondelete="cascade")
    
        
class xx_car_parts_com_lines(models.Model):
    _name = 'wof.car.parts.com.lines'
  
    service_type_id = fields.Many2one('wof.service.type', string="نوع الخدمة",required=True, index=True)
    
    part_price = fields.Float(string="سعر الجزء")
    header_id = fields.Many2one('wo.car.parts',required=True, ondelete="cascade")
    
class xx_car_parts_sizes_lines(models.Model):
    _name = 'wof.car.parts.size.lines'
   
    
    default_qty = fields.Float(string="المقاس الافتراضي للجزء",)
   
    max_qty = fields.Float(string="الحد الاعلى للمقاس")
    min_qty = fields.Float(string="الحد الادنى للمقاس")
    header_id = fields.Many2one('wof.car.parts',required=True)
    
   

    @api.constrains('default_qty','min_qty','max_qty')
    def check_qty(self):
        for rec in self:
            if rec.default_qty:
                if rec.max_qty or rec.min_qty:
                    if (rec.default_qty < rec.min_qty or rec.default_qty > rec.max_qty):
                        raise ValidationError(" تنبيه... يجب ان يكون الكمية الافتراضية بين الحد الاعلى والحد الادنى")
   
    