# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.osv import expression


class CarParts(models.Model):
    _name = 'wof.car.parts'
    _description = 'Car Part'
    _order = 'priority_part,name'
    
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
    priority_part = fields.Integer(string="ترتيب الاولوية", index = True)
 
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
    product_id = fields.Many2one(
        'product.product',
        string="الصنف الخدمي",
        domain=[('type', '!=', 'product')],
        required=True
    )
    # ================= PRICING & COMMISSION =================
    commission = fields.Float(string="عمولة الفني (%)")
    
    # ================= FLAGS =================
    active = fields.Boolean(default=True)
    car_part = fields.Boolean(string="جزء سيارة")
    car_category_part_flag = fields.Boolean(string="منطقة خدمة")
  
    part_options_required = fields.Boolean(string="الخيارات الإضافية إجبارية")
    film_category_readonly = fields.Boolean(string="فيلم غير قابل للتعديل")
    
   
    # ================= NOTES =================
    notes = fields.Char(string="ملاحظات")
    warning_msg = fields.Char(string="رسالة تحذير")

    # ================= RELATIONS =================
    part_lines = fields.One2many('wof.car.parts.lines','header_id',required=True, ondelete="cascade")
    part_com_lines = fields.One2many('wof.car.parts.com.lines','header_id',required=True, ondelete="cascade")
    part_sizes_lines = fields.One2many('wof.car.parts.size.lines','header_id',required=True, ondelete="cascade")
 
    part_options_ids = fields.Many2many('wof.car.part.options', string="خيارات إضافية")
   
    _sql_constraints = [
        ("car_part_unique",
         "UNIQUE(name)",
         "تنبيه .. جزء السيارة تم اضافتة مسبقا لا يمكن الاستمرار"),  ]

   
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

    @api.constrains('product_id', 'name')
    def _check_product(self):
        for rec in self:
            if not rec.product_id and rec.name:
                rec.product_id = rec.create_product_of_part(rec.name)
    
    def create_product_of_part(self,part_name):
        prod = self.env['product.product'].search([('name','=', part_name)])
        if prod:
            prod.write({'service_package_service':True})
            return prod
        if not prod:
            prod_tmp = self.env['product.template'].create({'name':part_name,
                                                            'type': 'service',
                                                            'branch_required': True,
                                                            'branch_id': False,
                                                            'service_package_service':True, })
            prod_new = self.env['product.product'].search([('product_tmpl_id', '=', prod_tmp.id)])
            if prod_new:
               return prod_new

    # def car_part_properties(self, service_type, film_category_id, car_size_id, return_type):

    #     size_line = self._get_size_line(service_type, film_category_id, car_size_id)
    #     price_line = self._get_price_line(service_type, film_category_id, car_size_id)

    #     size_line = size_line or self
    #     price_line = price_line or self

    #     size_map = {
    #         "default_qty": size_line.default_qty or self.default_qty,
    #         "min_qty": size_line.min_qty or self.min_qty,
    #         "max_qty": size_line.max_qty or self.max_qty,
    #         "size_readonly": size_line.size_readonly or self.size_readonly,
    #     }

    #     price_map = {
    #         "part_price": price_line.part_price if price_line else False,
    #         "price_readonly": price_line.price_readonly if price_line else False,
    #         "commission": price_line.commission or self.commission,
    #         "discount_exceed_limit": price_line.discount_exceed_limit or self.discount_exceed_limit,
    #         "default_film_product_id": (
    #             price_line.car_film_product_id.id if price_line and price_line.car_film_product_id else False
    #         ),
    #         "limpid_film_product_id": (
    #             price_line.limpid_film_product_id.id if price_line and price_line.limpid_film_product_id else False
    #         ),
    #     }

    #     if return_type in size_map:
    #         return size_map[return_type]

    #     if return_type in price_map:
    #         return price_map[return_type]

    #     return False

    # def _get_size_line(self, service_type, film_category_id, car_size_id):
    #     return self.part_sizes_lines.filtered(lambda l: l.service_type.id == service_type.id and (
    #                 (l.car_size_id.id == car_size_id.id and l.films_category_id.id == film_category_id.id)
    #                 or (not l.car_size_id and l.films_category_id.id == film_category_id.id)
    #                 or (l.car_size_id.id == car_size_id.id and not l.films_category_id)
    #                 or (not l.car_size_id and not l.films_category_id)))[:1]


    # def _get_price_line(self, service_type, film_category_id, car_size_id):
    #     return self.part_com_lines.filtered(lambda l: l.service_type.id == service_type.id and (
    #                 (l.car_size_id.id == car_size_id.id and l.films_category_id.id == film_category_id.id)
    #                 or (not l.car_size_id and l.films_category_id.id == film_category_id.id)
    #                 or (l.car_size_id.id == car_size_id.id and not l.films_category_id)
    #                 or (not l.car_size_id and not l.films_category_id)))[:1]

 
# class CarPartsLines(models.Model):
#     _name = 'wof.car.parts.lines'
#     _description = 'Car Parts Lines'
#     _rec_name = 'name'
#     _order = 'id desc'

#     # ================= BASIC =================
#     name = fields.Char(string="اسم الخط", required=True)

#     default_selection = fields.Boolean(
#         string="افتراضي في أمر التركيب",
#         default=False
#     )

#     # ================= RELATION =================
#     header_id = fields.Many2one(
#         'wof.car.parts',
#         string="جزء السيارة",
#         required=True,
#         ondelete='cascade',
#         index=True
#     )

#     # ================= SUB LINES =================
#     sub_part_ids = fields.One2many(
#         'wof.car.parts.sub.parts',
#         'line_id',
#         string="الأجزاء الفرعية"
#     )

#     # ================= ACTION =================
#     # def action_open_sub_parts(self):
#     #     self.ensure_one()

#     #     action = self.env.ref(
#     #         'qimamhd_wo_v3.action_car_parts_line_sub_parts_v3'
#     #     ).read()[0]

#     #     action.update({
#     #         'domain': [('line_id', '=', self.id)],
#     #         'context': {
#     #             'default_line_id': self.id,
#     #             'default_header_id': self.header_id.id,
#     #         }
#     #     })

#     #     return action

# class CarPartsSubParts(models.Model):
#     _name = 'wof.car.parts.sub.parts'
#     _description = 'Car Parts Sub Parts'
#     _rec_name = 'car_part_id'

#     # ================= RELATIONS =================
#     line_id = fields.Many2one(
#         'wof.car.parts.lines',
#         string="Line",
#         required=True,
#         ondelete='cascade',
#         index=True
#     )

#     header_id = fields.Many2one('wof.car.parts',
#         related='line_id.header_id',
#         store=True,
#         readonly=True
#     )

#     service_type_id = fields.Many2one(
#         'wof.service.type',
#         string="نوع الخدمة",
#         related='header_id.service_type_id',
#         store=True,
#         readonly=True
#     )

#     # ================= CONFIG =================
#     car_part_id = fields.Many2one(
#         'wof.car.parts',
#         string="جزء السيارة",
#         required=True,
#         domain="[('service_type_id','=',service_type_id)]"
#     )

#     car_size_id = fields.Many2one(
#         'wof.car.size',
#         string="حجم السيارة"
#     )

#     film_category_id = fields.Many2one(
#         'wof.film.category',
#         string="نوع الفلم",
#         domain="[('service_type_id','=',service_type_id)]"
#     )

#     film_category_line_id = fields.Many2one(
#         'wof.film.category.lines',
#         string="كود المبيعات",
#         domain="[('header_id','=',film_category_id)]"
#     )

#     # ================= PRODUCT =================
#     default_film_product_id = fields.Many2one(
#         'product.product',
#         string="الصنف المخزني",
#         domain="[('type','=','product'),('measure_product','=',True)]"
#     )

#     package_film_category_line_id = fields.Many2one(
#         'wof.film.category.lines',
#         string="كود الباقة",
#         domain="[('header_id','=',film_category_id)]"
#     )

#     package_film_product_id = fields.Many2one(
#         'product.product',
#         string="صنف الباقة",
#         domain="[('type','=','product'),('measure_product','=',True)]"
#     )

#     # ================= FLAGS =================
#     is_effected_in_inventory = fields.Boolean(
#         related='film_category_id.is_effected_in_inventory',
#         store=True
#     )
         
# class CarPartsCommissionLines(models.Model):
#     _name = 'wof.car.parts.com.lines'
#     _description = 'Car Parts Commission Lines'
#     _rec_name = 'service_type_id'

#     # ================= RELATIONS =================
#     header_id = fields.Many2one(
#         'wof.car.parts',
#         required=True,
#         ondelete='cascade',
#         index=True
#     )

#     service_type_id = fields.Many2one(
#         'wof.service.type',
#         string="نوع الخدمة",
#         required=True
#     )

#     film_category_id = fields.Many2one(
#         'wof.film.category',
#         string="نوع الفلم",
#         domain="[('service_type_id','=',service_type_id)]"
#     )

#     car_size_id = fields.Many2one(
#         'wof.car.size',
#         string="حجم السيارة"
#     )

#     # ================= PRICING =================
#     part_price = fields.Float(string="سعر الجزء")
#     commission = fields.Float(string="عمولة الفني")
#     discount_exceed_limit = fields.Integer(string="نسبة الخصم المسموح")

#     price_readonly = fields.Boolean(string="السعر ثابت")

#     # ================= PRODUCTS =================
#     film_category_line_id = fields.Many2one(
#         'wof.film.category.lines',
#         string="كود المبيعات",
#         domain="[('header_id','=',film_category_id)]"
#     )

#     limpid_film_product_id = fields.Many2one(
#         'product.product',
#         string="الصنف المخزني",
#         domain="[('type','=','product'),('measure_product','=',True)]"
#     )

#     package_film_product_id = fields.Many2one(
#         'product.product',
#         string="صنف الباقة",
#         domain="[('type','=','product'),('measure_product','=',True)]"
#     )

#     # ================= INVENTORY FLAG =================
#     is_effected_in_inventory = fields.Boolean(
#         related='film_category_id.is_effected_in_inventory',
#         store=True
#     )

#     # ================= CONSTRAINT =================
#     _sql_constraints = [
#         (
#             'unique_commission_rule',
#             'unique(service_type_id, film_category_id, car_size_id, header_id)',
#             'هذا السجل موجود مسبقاً لهذه الإعدادات'
#         )
#     ]
 

# class CarPartsSizeLines(models.Model):
    _name = 'wof.car.parts.size.lines'
    _description = 'Car Parts Size Rules'

    # ================= RELATIONS =================
    header_id = fields.Many2one(
        'wof.car.parts',
        required=True,
        ondelete='cascade',
        index=True
    )

    service_type_id = fields.Many2one('wof.service.type',
        related='header_id.service_type_id',
        store=True,
        readonly=True
    )

    film_category_id = fields.Many2one(
        'wof.film.category',
        string="نوع الفلم",
        domain="[('service_type_id','=',service_type_id)]"
    )

    car_size_id = fields.Many2one(
        'wof.car.size',
        string="حجم السيارة",
        required=True
    )

    # ================= QUANTITIES =================
    default_qty = fields.Float(string="المقاس الافتراضي")
    min_qty = fields.Float(string="الحد الأدنى")
    max_qty = fields.Float(string="الحد الأعلى")

    size_readonly = fields.Boolean(string="المقاس ثابت")

    # ================= FLAGS =================
    is_effected_in_inventory = fields.Boolean(
        related='film_category_id.is_effected_in_inventory',
        store=True
    )

    # ================= CONSTRAINT =================
    _sql_constraints = [
        (
            'unique_size_rule',
            'unique(service_type_id, film_category_id, car_size_id, header_id)',
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