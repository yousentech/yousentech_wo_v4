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

    service_type_id = fields.Many2one('wof.service.type', string="نوع الخدمة",required=True, index=True)
    warranty_years = fields.Char(string="فترة الضمان")

    is_effected_in_inventory = fields.Boolean(default=False,string="الفلم يؤثر على المخزون")
    car_film_product_required = fields.Boolean(default=False,string="كود المبيعات اجباري في امر التركيب")
    film_category_line_ids = fields.One2many('wof.film.category.lines','header_id' , ondelete="cascade")
    
    warning_film_line_ids = fields.Many2many('wof.film.category.lines',string="درجة اللون")
    warning_msg = fields.Char(string="رسالة تحذير")

    film_part_line_ids = fields.One2many('wof.film.parts.lines','header_id' , ondelete="cascade")
    film_part_size_line_ids = fields.One2many('wof.film.parts.size.lines','header_id' , ondelete="cascade")


    limpid_film_product_ids = fields.Many2many('product.product', string="الصنف المخزني",domain="[('measure_product','=',True),('type','=','product')]")

    heat_insulation = fields.Boolean(related="service_type_id.heat_insulation")

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
    

class FilmCategoryLine(models.Model):
    _name = 'wof.film.category.lines'
    _rec_name = 'name'

    name = fields.Char(string="درجة اللون", )
    limpid_product_ids = fields.Many2many('product.product',domain=[('measure_product','=', True),('type','=','product')],   string="الصنف المخزني", )
    header_id = fields.Many2one('wof.film.category',ondelete="cascade")

    _sql_constraints = [
        ("film_cat_line_unique",
         "UNIQUE(name,header_id)",
        "هذا السطر مضاف مسبقاً لنفس الفئة"),
    ]


class CarPartsCommissionLines(models.Model):
    _name = 'wof.film.parts.lines'
    _description = 'Car film Parts Lines'
    _rec_name = 'car_part_id'

    # ================= RELATIONS =================
    car_part_id = fields.Many2one(
        'wof.car.parts',
        required=True,
        ondelete='cascade',
        index=True
    ) 
     
    car_size_id = fields.Many2one(
        'wof.car.size',
        string="حجم السيارة"
    )

    # ================= PRICING =================
    part_price = fields.Float(string="سعر الجزء")
    commission = fields.Float(string="عمولة الفني")
    discount_exceed_limit = fields.Integer(string="نسبة الخصم المسموح")

    price_readonly = fields.Boolean(string="السعر ثابت")

    # ================= PRODUCTS =================
    film_category_line_id = fields.Many2one(
        'wof.film.category.lines',
        string="كود المبيعات",
        domain="[('header_id','=',header_id)]"
    )

    
 
    # ================= INVENTORY FLAG =================
    is_effected_in_inventory = fields.Boolean(
        related='header_id.is_effected_in_inventory',
        store=True
    )

     # ================= RELATIONS =================
    header_id = fields.Many2one('wof.film.category',ondelete="cascade")




    # ================= CONSTRAINT =================
    _sql_constraints = [
        (
            'unique_commission_rule',
            'unique(car_part_id, header_id, car_size_id)',
            'هذا السجل موجود مسبقاً لهذه الإعدادات'
        )
    ]


    
class CarPartssizeLines(models.Model):
    _name = 'wof.film.parts.size.lines'
    _description = 'Car film Parts size Lines'
    _rec_name = 'car_part_id'

    # ================= RELATIONS =================
    car_part_id = fields.Many2one(
        'wof.car.parts',
        required=True,
        ondelete='cascade',
        index=True,
        domain="[('id', 'in', available_part_ids)]" )
     
    car_size_id = fields.Many2one(
        'wof.car.size',
        string="حجم السيارة"
    )
    available_part_ids = fields.Many2many('wof.car.parts', compute='_compute_available_parts')

    # ================= QUANTITIES =================
    default_qty = fields.Float(string="المقاس الافتراضي")
    min_qty = fields.Float(string="الحد الأدنى")
    max_qty = fields.Float(string="الحد الأعلى")

    size_readonly = fields.Boolean(string="المقاس ثابت")

    
     # ================= RELATIONS =================
    header_id = fields.Many2one('wof.film.category',ondelete="cascade")



 # ================= CONSTRAINT =================
    _sql_constraints = [
        (
            'unique_size_rule',
            'unique(car_part_id, car_size_id, header_id)',
            'هذا السجل موجود مسبقاً لنفس الإعدادات'
        )
    ]

    # ================= VALIDATION =================
    @api.constrains('default_qty', 'min_qty', 'max_qty')
    def _check_qty_range(self):
        for rec in self:

            if rec.min_qty and rec.max_qty and rec.default_qty:

                if not (rec.min_qty <= rec.default_qty <= rec.max_qty):
                    raise ValidationError(
                        "المقاس الافتراضي يجب أن يكون بين الحد الأدنى والأعلى"
                    )

    @api.depends('header_id')
    def _compute_available_parts(self):
        for rec in self:
            if rec.header_id:
                rec.available_part_ids = rec.header_id.film_part_line_ids.mapped('car_part_id')
            else:
                rec.available_part_ids = False