# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class film_category(models.Model):
    _name = 'wof.film.category'
    _description = 'Film Category'
    _rec_name = 'name'
    _order = 'code,name'
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

    service_type_id = fields.Many2one('wof.service.type', string="نوع الخدمة",required=True, index=True,ondelete='restrict',)
    warranty_years = fields.Char(string="فترة الضمان")

    is_effected_in_inventory = fields.Boolean(default=False,string="الفلم يؤثر على المخزون")
    car_film_product_required = fields.Boolean(default=False,string="كود المبيعات اجباري في امر التركيب")
    film_category_line_ids = fields.One2many('wof.film.category.lines','header_id'  )
    
   
    film_part_line_ids = fields.One2many('wof.film.parts.lines','header_id' )
    film_part_size_line_ids = fields.One2many('wof.film.parts.size.lines','header_id' )

    warning_film_line_ids = fields.Many2many('wof.film.category.lines',string="درجة اللون")
    warning_msg = fields.Char(string="رسالة تحذير")


    limpid_film_product_ids = fields.Many2many('product.product', string="الصنف المخزني",domain="[('measure_product','=',True),('type','=','product')]")
    service_options = fields.Selection([('tint','عزل حراري'),
                                        ('ppf','حماية'),
                                        ('nano','نانو سيراميك'),
                                        ('upholstery','تنجيد'),
                                        ('floor_mats','أرضيات'),
                                        ('others','أخرى')],string="النوع",default='tint',required=True,related="service_type_id.service_options")
  

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


    parts_count = fields.Integer(
        string="عدد الأجزاء",
        compute="_compute_parts_count"
    )

    def _compute_parts_count(self):
        data = self.env['wof.film.parts.lines'].read_group(
            [('header_id', 'in', self.ids)],
            ['header_id'],
            ['header_id']
        )

        mapped = {
            d['header_id'][0]: d['header_id_count']
            for d in data
        }

        for rec in self:
            rec.parts_count = mapped.get(rec.id, 0)
            

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

    @api.constrains('is_effected_in_inventory', 'limpid_film_product_ids')
    def _check_inventory_products(self):
        for rec in self:
            if rec.is_effected_in_inventory and not rec.limpid_film_product_ids:
                raise ValidationError("تنبيه: يجب تحديد الصنف مخزني إذا الفلم يؤثر على المخزون")
    

class CarPartsLines(models.Model):
    _name = 'wof.film.parts.lines'
    _description = 'Car Film Parts'
    _rec_name = 'car_part_id'
    _order = 'header_id, car_part_id'

    service_type_id = fields.Many2one(
        'wof.service.type',
        related='header_id.service_type_id',
        store=True,
        index=True
    )

    header_id = fields.Many2one(
        'wof.film.category',
        string="نوع الفلم",
        required=True,
        ondelete="cascade",
        index=True
    )

    part_selected = fields.Boolean(
        string="تفعيل",
        default=True
    )

    car_part_id = fields.Many2one(
        'wof.car.parts',
        string="الجزء",
        required=True,
        ondelete='restrict',
        index=True
    )

    film_category_line_id = fields.Many2one(
        'wof.film.category.lines',
        string="درجة اللون",
        domain="[('header_id','=',header_id)]"
    )

    is_effected_in_inventory = fields.Boolean(
        related='header_id.is_effected_in_inventory',
        store=True
    )

    price_line_ids = fields.One2many(
        'wof.film.parts.price.lines',
        'part_line_id',
        string="التسعيرات"
    )

    commission_line_ids = fields.One2many(
        'wof.film.parts.commission.lines',
        'part_line_id',
        string="العمولات"
    )

    price_count = fields.Integer(
        string="عدد التسعيرات",
        compute="_compute_counts"
    )

    commission_count = fields.Integer(
        string="عدد العمولات",
        compute="_compute_counts"
    )

    _sql_constraints = [
        (
            'unique_film_part_rule',
            'unique(car_part_id, header_id)',
            'هذا الجزء موجود مسبقاً لنفس الفلم'
        ),
    ]

    def _compute_counts(self):
        for rec in self:
            rec.price_count = len(rec.price_line_ids)
            rec.commission_count = len(rec.commission_line_ids)

    def action_open_price_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'تسعيرات الجزء',
            'res_model': 'wof.film.parts.price.lines',
            'view_mode': 'tree,form',
            'domain': [('part_line_id', '=', self.id)],
            'context': {
                'default_part_line_id': self.id,
                'default_header_id': self.header_id.id,
                'default_car_part_id': self.car_part_id.id,
            },
            'target': 'current',
        }

    def action_open_commission_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'عمولات الجزء',
            'res_model': 'wof.film.parts.commission.lines',
            'view_mode': 'tree,form',
            'domain': [('part_line_id', '=', self.id)],
            'context': {
                'default_part_line_id': self.id,
                'default_header_id': self.header_id.id,
                'default_car_part_id': self.car_part_id.id,
            },
            'target': 'current',
        }


class FilmPartPriceLines(models.Model):
    _name = 'wof.film.parts.price.lines'
    _description = 'Film Part Price Lines'
    _rec_name = 'car_part_id'
    _order = 'part_line_id, car_size_id'

    part_line_id = fields.Many2one(
        'wof.film.parts.lines',
        string="سطر الجزء",
        required=True,
        ondelete='cascade',
        index=True
    )

    header_id = fields.Many2one(
        'wof.film.category',
        string="نوع الفلم",
        related='part_line_id.header_id',
        store=True,
        index=True
    )

    service_type_id = fields.Many2one(
        'wof.service.type',
        related='part_line_id.service_type_id',
        store=True,
        index=True
    )

    car_part_id = fields.Many2one(
        'wof.car.parts',
        string="الجزء",
        related='part_line_id.car_part_id',
        store=True,
        index=True
    )

    car_size_id = fields.Many2one(
        'wof.car.size',
        string="حجم السيارة",
        ondelete='restrict',
        index=True
    )

    part_price = fields.Float(string="سعر الجزء")
    discount_exceed_limit = fields.Integer(string="نسبة الخصم المسموح")

    tax_id = fields.Many2one(
        'account.tax',
        string="الضريبة",
        ondelete='restrict',
        domain=[('type_tax_use', '=', 'sale')]
    )

    price_readonly = fields.Boolean(string="السعر ثابت")
    free_part = fields.Boolean(string="جزء مجاني")

    _sql_constraints = [
        (
            'unique_film_part_price_size_rule',
            'unique(part_line_id, car_size_id)',
            'تسعيرة هذا الحجم مضافة مسبقاً لهذا الجزء'
        ),
    ]

    @api.onchange('free_part')
    def _onchange_free_part(self):
        for rec in self:
            if rec.free_part:
                rec.part_price = 0.0
                rec.tax_id = False


class FilmPartCommissionLines(models.Model):
    _name = 'wof.film.parts.commission.lines'
    _description = 'Film Part Commission Lines'
    _rec_name = 'car_part_id'
    _order = 'part_line_id, car_size_id'

    part_line_id = fields.Many2one(
        'wof.film.parts.lines',
        string="سطر الجزء",
        required=True,
        ondelete='cascade',
        index=True
    )

    header_id = fields.Many2one(
        'wof.film.category',
        string="نوع الفلم",
        related='part_line_id.header_id',
        store=True,
        index=True
    )

    service_type_id = fields.Many2one(
        'wof.service.type',
        related='part_line_id.service_type_id',
        store=True,
        index=True
    )

    car_part_id = fields.Many2one(
        'wof.car.parts',
        string="الجزء",
        related='part_line_id.car_part_id',
        store=True,
        index=True
    )

    car_size_id = fields.Many2one(
        'wof.car.size',
        string="حجم السيارة",
        ondelete='restrict',
        index=True
    )

    commission = fields.Float(string="عمولة الفني")

    _sql_constraints = [
        (
            'unique_film_part_commission_size_rule',
            'unique(part_line_id, car_size_id)',
            'عمولة هذا الحجم مضافة مسبقاً لهذا الجزء'
        ),
    ]