# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class film_category(models.Model):
    _name = 'wof.film.category'
    _description = 'Film Category'
    _rec_name = 'name'
    _order = 'code,name'
    _company_auto = True

    code = fields.Char(string="الكود", index=True, copy=False)

    name = fields.Char(
        string="الاسم",
        required=True,
        index=True,
        translate=True,
        tracking=True
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

    active = fields.Boolean(string="تفعيل", default=True)

    service_type_id = fields.Many2one(
        'wof.service.type',
        string="نوع الخدمة",
        required=True,
        index=True,
        ondelete='restrict'
    )

    warranty_duration = fields.Integer(
        string="مدة الضمان",
        default=5
    )

    warranty_period = fields.Selection([
        ('day', 'يوم'),
        ('month', 'شهر'),
        ('year', 'سنة'),
        ('lifetime', 'مدى الحياة'),
    ], string="نوع مدة الضمان", default='year', required=True)

    warranty_years = fields.Char(
        string="مدة الضمان نصياً",
        compute="_compute_warranty_years",
        store=True
    )

    @api.depends('warranty_duration', 'warranty_period')
    def _compute_warranty_years(self):
        labels = dict(self._fields['warranty_period'].selection)
        for rec in self:
            if rec.warranty_period == 'lifetime':
                rec.warranty_years = _('مدى الحياة')
            else:
                rec.warranty_years = "%s %s" % (
                    rec.warranty_duration or 0,
                    labels.get(rec.warranty_period, '')
                )

    is_effected_in_inventory = fields.Boolean(
        default=False,
        string="الفلم يؤثر على المخزون"
    )

    car_film_product_required = fields.Boolean(
        default=False,
        string="كود المبيعات اجباري في امر التركيب"
    )

    film_category_line_ids = fields.One2many(
        'wof.film.category.lines',
        'header_id'
    )

    film_part_line_ids = fields.One2many(
        'wof.film.parts.lines',
        'header_id',
        string="الأجزاء"
    )

    film_part_size_line_ids = fields.One2many(
        'wof.film.parts.size.lines',
        'header_id',
        string="المقاسات الافتراضية"
    )

    warning_film_line_ids = fields.Many2many(
        'wof.film.category.lines',
        string="درجة اللون"
    )

    warning_msg = fields.Char(string="رسالة تحذير")

    limpid_film_product_ids = fields.Many2many(
        'product.product',
        string="الصنف المخزني",
        domain="[('measure_product','=',True),('type','=','product')]"
    )

    service_options = fields.Selection(
        related="service_type_id.service_options",
        string="النوع",
        store=True,
        readonly=True
    )

    parts_count = fields.Integer(
        string="عدد الأجزاء",
        compute="_compute_parts_count"
    )

    _sql_constraints = [
        (
            'film_category_unique',
            "UNIQUE(name, company_id)",
            "نوع الفلم مضاف مسبقاً لنفس الشركة"
        ),
        (
            'film_category_code_unique',
            "UNIQUE(code, company_id)",
            "الكود مستخدم مسبقاً"
        ),
    ]

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
            display_name = "[%s] %s" % (rec.code, rec.name) if rec.code else rec.name
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
            ] + args
        else:
            domain = args

        records = self.search(domain, limit=limit)
        if records:
            return records.name_get()

        return super().name_search(name, args=args, operator=operator, limit=limit)

    @api.constrains('is_effected_in_inventory', 'limpid_film_product_ids')
    def _check_inventory_products(self):
        for rec in self:
            if rec.is_effected_in_inventory and not rec.limpid_film_product_ids:
                raise ValidationError("تنبيه: يجب تحديد الصنف مخزني إذا الفلم يؤثر على المخزون")


class FilmCategoryLine(models.Model):
    _name = 'wof.film.category.lines'
    _description = 'Film Category Color Lines'
    _rec_name = 'name'

    name = fields.Char(string="درجة اللون")

    limpid_product_ids = fields.Many2many('product.product', domain=[('measure_product', '=', True), ('type', '=', 'product')],  string="الصنف المخزني" )

    header_id = fields.Many2one('wof.film.category', ondelete="cascade",  string="الفلم" )

    _sql_constraints = [
        ("film_cat_line_unique", "UNIQUE(name,header_id)",
            "هذا السطر مضاف مسبقاً لنفس الفئة" )]


class FilmPartLines(models.Model):
    _name = 'wof.film.parts.lines'
    _description = 'Film Parts Lines'
    _rec_name = 'car_part_id'
    _order = 'header_id, car_part_id'

    header_id = fields.Many2one(
        'wof.film.category',
        string="نوع الفلم",
        required=True,
        ondelete="cascade",
        index=True
    )

    service_type_id = fields.Many2one(
        'wof.service.type',
        related='header_id.service_type_id',
        store=True,
        index=True,
        readonly=True
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
        store=True,
        readonly=True
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

    price_widget_trigger = fields.Char(
        string="التسعيرات",
        compute="_compute_widget_trigger"
    )

    commission_widget_trigger = fields.Char(
        string="العمولات",
        compute="_compute_widget_trigger"
    )

    def _compute_widget_trigger(self):
        for rec in self:
            rec.price_widget_trigger = "open"
            rec.commission_widget_trigger = "open"



    def _compute_counts(self):
        for rec in self:
            rec.price_count = len(rec.price_line_ids)
            rec.commission_count = len(rec.commission_line_ids)

    def action_open_price_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('تسعيرات الجزء'),
            'res_model': 'wof.film.parts.price.lines',
            'view_mode': 'tree,form',
            'domain': [('part_line_id', '=', self.id)],
            'context': {
                'default_part_line_id': self.id,
            },
            'target': 'new',
        }

    def action_open_commission_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('عمولات الجزء'),
            'res_model': 'wof.film.parts.commission.lines',
            'view_mode': 'tree,form',
            'domain': [('part_line_id', '=', self.id)],
            'context': {
                'default_part_line_id': self.id,
            },
            'target': 'new',
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
        related='part_line_id.header_id',
        string="نوع الفلم",
        store=True,
        index=True,
        readonly=True
    )

    service_type_id = fields.Many2one(
        'wof.service.type',
        related='part_line_id.service_type_id',
        store=True,
        index=True,
        readonly=True
    )

    car_part_id = fields.Many2one(
        'wof.car.parts',
        related='part_line_id.car_part_id',
        string="الجزء",
        store=True,
        index=True,
        readonly=True
    )

    car_size_id = fields.Many2one(
        'wof.car.size',
        string="حجم السيارة",
        ondelete='restrict',
        index=True
    )

    free_part = fields.Boolean(string="جزء مجاني")
    part_price = fields.Float(string="سعر الجزء")
    discount_exceed_limit = fields.Integer(string="نسبة الخصم المسموح")

    tax_id = fields.Many2one(
        'account.tax',
        string="الضريبة",
        ondelete='restrict',
        domain=[('type_tax_use', '=', 'sale')]
    )

    price_readonly = fields.Boolean(string="السعر ثابت")

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
                rec.price_readonly = True
                rec.discount_exceed_limit = 0.0
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
        related='part_line_id.header_id',
        string="نوع الفلم",
        store=True,
        index=True,
        readonly=True
    )

    service_type_id = fields.Many2one(
        'wof.service.type',
        related='part_line_id.service_type_id',
        store=True,
        index=True,
        readonly=True
    )

    car_part_id = fields.Many2one(
        'wof.car.parts',
        related='part_line_id.car_part_id',
        string="الجزء",
        store=True,
        index=True,
        readonly=True
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


class CarPartssizeLines(models.Model):
    _name = 'wof.film.parts.size.lines'
    _description = 'Car Film Parts Size Lines'
    _rec_name = 'car_part_id'

    header_id = fields.Many2one(
        'wof.film.category',
        ondelete="cascade",
        string="الفلم"
    )

    available_part_ids = fields.Many2many(
        'wof.car.parts',
        compute='_compute_available_parts'
    )

    car_part_id = fields.Many2one(
        'wof.car.parts',
        required=True,
        ondelete='restrict',
        index=True,
        domain="[('id', 'in', available_part_ids)]"
    )

    car_size_id = fields.Many2one(
        'wof.car.size',
        ondelete='restrict',
        string="حجم السيارة"
    )

    default_qty = fields.Float(string="المقاس الافتراضي")
    min_qty = fields.Float(string="الحد الأدنى")
    max_qty = fields.Float(string="الحد الأعلى")
    size_readonly = fields.Boolean(string="المقاس ثابت")

    _sql_constraints = [
        (
            'unique_size_rule',
            'unique(car_part_id, car_size_id, header_id)',
            'هذا السجل موجود مسبقاً لنفس الإعدادات'
        )
    ]

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

class WofSetupPartsModeConfirmWizard(models.TransientModel):
    _name = 'wof.setup.parts.mode.confirm.wizard'
    _description = 'WOF Setup Parts Mode Confirm Wizard'

    setup_film_wizard_id = fields.Many2one(
        'wof.setup.film.wizard',
        string="معالج الفيلم",
        required=True,
        ondelete='cascade'
    )

    message = fields.Text(
        string="الرسالة",
        readonly=True
    )

    def action_continue_commission(self):
        self.ensure_one()

        setup = self.setup_film_wizard_id
        setup.parts_mode = 'commission'

        return setup._reload_film_wizard()

    def action_keep_pricing(self):
        self.ensure_one()

        setup = self.setup_film_wizard_id
        setup.parts_mode = 'pricing'

        return setup._reload_film_wizard()