# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class film_category(models.Model):
    _name = 'wof.film.category'
    _description = 'Film Category'
    _rec_name = 'name'
    _order = 'name'
    _company_auto = True   # 👈 هنا المكان الصحيح
    
    code = fields.Char(
        string="الكود",
        index=True,
        copy=False
    )
    name = fields.Char(
        string="الاسم",
        required=True,
        index=True,
        translate=True,   # 👈 مهم لو عندك لغات
        tracking=True     # 👈 لو تستخدم chatter
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

    service_type = fields.Many2one('wof.service.type', string="نوع الخدمة",required=True, index=True)
    warranty_years = fields.Char(string="فترة الضمان")

    is_effected_in_inventory = fields.Boolean(default=False,string="الفلم يؤثر على المخزون")
    car_film_product_required = fields.Boolean(default=False,string="كود المبيعات اجباري في امر التركيب")
    film_category_line_ids = fields.One2many('wof.film.category.lines','header_id' , ondelete="cascade")
    limpid_film_product_id = fields.Many2many('product.product', string="الصنف المخزني",domain="[('measure_product','=',True),('type','=','product')]")


    _sql_constraints = [
        (
            'film_category_unique',
            "UNIQUE(name, company_id)",  # 👈 مهم جداً multi-company
            "نوع الفلم مضاف مسبقاً لنفس الشركة"
        ),
        (
            'film_category_code_unique',
            "UNIQUE(code, company_id)",
            "الكود مستخدم مسبقاً"
        ),
    ]

    def name_get(self):
        result = []
        for rec in self:
            name = rec.name or ''
            if rec.code:
                name = f"[{rec.code}] {name}"
            result.append((rec.id, name))
        return result

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        args = args or []

        if name:
            args = ['|', ('name', operator, name), ('code', operator, name)] + args

        return super().name_search(name='', args=args, operator=operator, limit=limit)

    @api.constrains('is_effected_in_inventory', 'limpid_film_product_id')
    def _check_inventory_products(self):
        for rec in self:
            if rec.is_effected_in_inventory and not rec.limpid_film_product_id:
                raise ValidationError("تنبيه: يجب تحديد الصنف مخزني إذا الفلم يؤثر على المخزون")
    

class FilmCategoryLine(models.Model):
    _name = 'wof.film.category.lines'
    _rec_name = 'name'

    name = fields.Char(string="الاسم", )
    limpid_product_ids = fields.Many2many('product.product',domain=[('measure_product','=', True),('type','=','product')],   string="الصنف المخزني", )
    header_id = fields.Many2one('wof.film.category',ondelete="cascade")

    _sql_constraints = [
        ("film_cat_line_unique",
         "UNIQUE(name,header_id)",
        "هذا السطر مضاف مسبقاً لنفس الفئة"),
    ]