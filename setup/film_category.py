# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FilmCategory(models.Model):
    _name = 'wof.film.category'
    _inherit = ['wof.api.mixin']
    _description = 'فئة فيلم'
    _order = 'service_type_id, sequence, name'
    _check_company_auto = True

    sequence = fields.Integer(default=10)
    name = fields.Char(string="اسم الفيلم", required=True, index=True, translate=True)
    code = fields.Char(string="الكود", required=True, index=True, copy=False)
    service_type_id = fields.Many2one(
        'wof.service.type', string="نوع الخدمة", required=True,
        ondelete='restrict', check_company=True, index=True,
    )
    service_options = fields.Selection(
        related='service_type_id.service_options', string="النشاط", store=True,
    )
    warranty_years = fields.Integer(string="سنوات الضمان", default=5)
    is_effected_in_inventory = fields.Boolean(string="يصرف مواد من المخزون")
    car_film_product_required = fields.Boolean(string="اختيار المنتج المخزني إلزامي")
    warning_msg = fields.Char(string="رسالة تنبيه")
    company_id = fields.Many2one(
        'res.company', related='service_type_id.company_id',
        store=True, readonly=True, index=True,
    )
    active = fields.Boolean(default=True)
    film_category_line_ids = fields.One2many(
        'wof.film.category.lines', 'header_id', string="درجات الفيلم والمنتجات",
    )
    film_part_line_ids = fields.One2many(
        'wof.film.parts.lines', 'header_id', string="الأجزاء والأسعار",
    )
    parts_count = fields.Integer(compute='_compute_counts')
    price_count = fields.Integer(compute='_compute_counts')
    commission_count = fields.Integer(compute='_compute_counts')

    _sql_constraints = [
        ('film_name_service_company_unique', 'unique(name, service_type_id, company_id)',
         'اسم الفيلم مستخدم مسبقًا لنفس الخدمة والشركة.'),
        ('film_code_company_unique', 'unique(code, company_id)',
         'كود الفيلم مستخدم مسبقًا في هذه الشركة.'),
        ('film_warranty_nonnegative', 'check(warranty_years >= 0)',
         'سنوات الضمان لا يمكن أن تكون سالبة.'),
    ]

    @api.depends('film_part_line_ids.price_line_ids', 'film_part_line_ids.commission_line_ids')
    def _compute_counts(self):
        for record in self:
            record.parts_count = len(record.film_part_line_ids)
            record.price_count = sum(len(line.price_line_ids) for line in record.film_part_line_ids)
            record.commission_count = sum(
                len(line.commission_line_ids) for line in record.film_part_line_ids
            )

    def action_open_price_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': 'تسعيرات الأجزاء',
            'res_model': 'wof.film.parts.price.lines', 'view_mode': 'tree,form',
            'domain': [('header_id', '=', self.id)],
            'context': {'wof_default_film_id': self.id},
        }

    def action_open_commission_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': 'عمولات الأجزاء',
            'res_model': 'wof.film.parts.commission.lines', 'view_mode': 'tree,form',
            'domain': [('header_id', '=', self.id)],
            'context': {'wof_default_film_id': self.id},
        }


class FilmCategoryLine(models.Model):
    _name = 'wof.film.category.lines'
    _inherit = ['wof.api.mixin']
    _description = 'درجة فيلم ومنتج'
    _order = 'sequence, name'
    _check_company_auto = True

    sequence = fields.Integer(default=10)
    header_id = fields.Many2one(
        'wof.film.category', string="الفيلم", required=True,
        ondelete='cascade', check_company=True, index=True,
    )
    name = fields.Char(string="الدرجة أو اللون", required=True)
    code = fields.Char(string="الكود", required=True, index=True, copy=False)
    product_id = fields.Many2one(
        'product.product', string="المنتج المخزني",
        ondelete='restrict', check_company=True,
    )
    company_id = fields.Many2one(
        related='header_id.company_id', store=True, readonly=True, index=True,
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('film_grade_name_unique', 'unique(header_id, name)',
         'هذه الدرجة أو اللون مضافة مسبقًا لنفس الفيلم.'),
        ('film_grade_code_unique', 'unique(header_id, code)',
         'كود الدرجة أو اللون مستخدم مسبقًا لنفس الفيلم.'),
    ]


class FilmPartLine(models.Model):
    _name = 'wof.film.parts.lines'
    _inherit = ['wof.api.mixin']
    _description = 'جزء مرتبط بفيلم'
    _rec_name = 'car_part_id'
    _order = 'header_id, sequence, car_part_id'
    _check_company_auto = True

    sequence = fields.Integer(default=10)
    header_id = fields.Many2one(
        'wof.film.category', string="الفيلم", required=True,
        ondelete='cascade', check_company=True, index=True,
    )
    service_type_id = fields.Many2one(
        related='header_id.service_type_id', store=True, readonly=True, index=True,
    )
    company_id = fields.Many2one(
        related='header_id.company_id', store=True, readonly=True, index=True,
    )
    part_selected = fields.Boolean(string="مفعّل", default=True)
    car_part_id = fields.Many2one(
        'wof.car.parts', string="الجزء", required=True,
        ondelete='restrict', check_company=True, index=True,
    )
    film_category_line_id = fields.Many2one(
        'wof.film.category.lines', string="الدرجة الافتراضية",
        domain="[('header_id', '=', header_id)]", check_company=True,
    )
    is_effected_in_inventory = fields.Boolean(
        related='header_id.is_effected_in_inventory', store=True,
    )
    price_line_ids = fields.One2many(
        'wof.film.parts.price.lines', 'part_line_id', string="التسعيرات",
    )
    commission_line_ids = fields.One2many(
        'wof.film.parts.commission.lines', 'part_line_id', string="العمولات",
    )
    price_count = fields.Integer(compute='_compute_counts')
    commission_count = fields.Integer(compute='_compute_counts')

    _sql_constraints = [
        ('film_part_unique', 'unique(car_part_id, header_id)',
         'هذا الجزء موجود مسبقًا لنفس الفيلم.'),
    ]

    @api.depends('price_line_ids', 'commission_line_ids')
    def _compute_counts(self):
        for record in self:
            record.price_count = len(record.price_line_ids)
            record.commission_count = len(record.commission_line_ids)

    @api.model
    def name_get(self):
        return [
            (
                record.id,
                '%s / %s' % (
                    record.header_id.display_name,
                    record.car_part_id.display_name,
                ),
            )
            for record in self
        ]

    def action_open_price_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': 'تسعير الجزء حسب الحجم',
            'res_model': 'wof.film.parts.price.lines', 'view_mode': 'tree,form',
            'domain': [('part_line_id', '=', self.id)],
            'context': {'default_part_line_id': self.id},
        }

    def action_open_commission_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': 'عمولة الجزء حسب الحجم',
            'res_model': 'wof.film.parts.commission.lines', 'view_mode': 'tree,form',
            'domain': [('part_line_id', '=', self.id)],
            'context': {'default_part_line_id': self.id},
        }


class FilmPartPriceLine(models.Model):
    _name = 'wof.film.parts.price.lines'
    _inherit = ['wof.api.mixin']
    _description = 'تسعير جزء فيلم'
    _rec_name = 'car_part_id'
    _order = 'part_line_id, car_size_id'
    _check_company_auto = True

    part_line_id = fields.Many2one(
        'wof.film.parts.lines', string="الجزء", required=True,
        ondelete='cascade', check_company=True, index=True,
    )
    header_id = fields.Many2one(related='part_line_id.header_id', store=True, readonly=True)
    service_type_id = fields.Many2one(
        related='part_line_id.service_type_id', store=True, readonly=True,
    )
    car_part_id = fields.Many2one(
        related='part_line_id.car_part_id', store=True, readonly=True,
    )
    company_id = fields.Many2one(
        related='part_line_id.company_id', store=True, readonly=True, index=True,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id', store=True, readonly=True,
    )
    car_size_id = fields.Many2one(
        'wof.car.size', string="حجم السيارة",
        ondelete='restrict', check_company=True, index=True,
    )
    part_price = fields.Monetary(string="السعر", currency_field='currency_id')
    discount_exceed_limit = fields.Integer(string="حد الخصم %")
    tax_id = fields.Many2one(
        'account.tax', string="الضريبة", ondelete='restrict',
        check_company=True, domain=[('type_tax_use', '=', 'sale')],
    )
    price_readonly = fields.Boolean(string="السعر ثابت")
    free_part = fields.Boolean(string="مجاني")

    _sql_constraints = [
        ('film_part_price_size_unique', 'unique(part_line_id, car_size_id)',
         'تسعيرة هذا الحجم مضافة مسبقًا لهذا الجزء.'),
        ('film_part_price_nonnegative', 'check(part_price >= 0)',
         'السعر لا يمكن أن يكون سالبًا.'),
        ('film_part_discount_range',
         'check(discount_exceed_limit >= 0 AND discount_exceed_limit <= 100)',
         'حد الخصم يجب أن يكون بين 0 و100.'),
    ]

    @api.onchange('free_part')
    def _onchange_free_part(self):
        for record in self:
            if record.free_part:
                record.part_price = 0.0
                record.tax_id = False

    @api.constrains('free_part', 'part_price', 'tax_id')
    def _check_free_part_price(self):
        for record in self:
            if record.free_part and record.part_price:
                raise ValidationError('الجزء المجاني يجب أن يكون سعره صفرًا.')
            if record.free_part and record.tax_id:
                raise ValidationError('الجزء المجاني يجب ألا يحمل ضريبة.')

    @api.constrains('part_line_id', 'car_size_id')
    def _check_unique_size_including_default(self):
        for record in self:
            domain = [('part_line_id', '=', record.part_line_id.id)]
            domain.append(
                ('car_size_id', '=', record.car_size_id.id)
                if record.car_size_id else ('car_size_id', '=', False)
            )
            if self.search_count(domain) > 1:
                raise ValidationError(
                    'يوجد سعر لنفس الجزء وحجم السيارة مسبقًا.'
                )


class FilmPartCommissionLine(models.Model):
    _name = 'wof.film.parts.commission.lines'
    _inherit = ['wof.api.mixin']
    _description = 'عمولة جزء فيلم'
    _rec_name = 'car_part_id'
    _order = 'part_line_id, car_size_id'
    _check_company_auto = True

    part_line_id = fields.Many2one(
        'wof.film.parts.lines', string="الجزء", required=True,
        ondelete='cascade', check_company=True, index=True,
    )
    header_id = fields.Many2one(related='part_line_id.header_id', store=True, readonly=True)
    service_type_id = fields.Many2one(
        related='part_line_id.service_type_id', store=True, readonly=True,
    )
    car_part_id = fields.Many2one(
        related='part_line_id.car_part_id', store=True, readonly=True,
    )
    company_id = fields.Many2one(
        related='part_line_id.company_id', store=True, readonly=True, index=True,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id', store=True, readonly=True,
    )
    car_size_id = fields.Many2one(
        'wof.car.size', string="حجم السيارة",
        ondelete='restrict', check_company=True, index=True,
    )
    commission = fields.Monetary(
        string="عمولة الفني", currency_field='currency_id',
    )

    _sql_constraints = [
        ('film_part_commission_size_unique', 'unique(part_line_id, car_size_id)',
         'عمولة هذا الحجم مضافة مسبقًا لهذا الجزء.'),
        ('film_part_commission_nonnegative', 'check(commission >= 0)',
         'العمولة لا يمكن أن تكون سالبة.'),
    ]

    @api.constrains('part_line_id', 'car_size_id')
    def _check_unique_size_including_default(self):
        for record in self:
            domain = [('part_line_id', '=', record.part_line_id.id)]
            domain.append(
                ('car_size_id', '=', record.car_size_id.id)
                if record.car_size_id else ('car_size_id', '=', False)
            )
            if self.search_count(domain) > 1:
                raise ValidationError(
                    'توجد عمولة لنفس الجزء وحجم السيارة مسبقًا.'
                )
