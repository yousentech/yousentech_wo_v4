# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FilmCategory(models.Model):
    _name = 'wof.film.category'
    _inherit = ['wof.api.mixin']
    _description = 'خدمة أو فيلم عناية'
    _order = 'service_type_id, sequence, name'
    _check_company_auto = True

    sequence = fields.Integer(default=10)
    name = fields.Char(string="اسم الخدمة / الفيلم", required=True, index=True, translate=True)
    code = fields.Char(string="الكود", required=True, index=True, copy=False)
    service_type_id = fields.Many2one(
        'wof.service.type', string="نشاط المركز", required=True,
        ondelete='restrict', check_company=True, index=True,
    )
    service_options = fields.Selection(
        related='service_type_id.service_options', string="النشاط", store=True,
    )
    supports_color_grades = fields.Boolean(
        related='service_type_id.supports_color_grades', readonly=True,
    )
    description = fields.Text(string="وصف الموظف", translate=True)
    item_type = fields.Selection(
        [('film', 'فيلم'), ('service', 'خدمة')],
        string="نوع العنصر", default='film', required=True, index=True,
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

    # Film/service configuration policy.  These fields preserve whether the
    # record inherits company setup or intentionally overrides it.
    use_system_pricing_policy = fields.Boolean(
        string="استخدام سياسة تسعير النظام", default=True,
    )
    pricing_policy = fields.Selection(
        [('fixed', 'سعر موحد'), ('by_size', 'حسب حجم السيارة')],
        string="سياسة التسعير", default='fixed', required=True,
    )
    use_system_car_sizes = fields.Boolean(
        string="استخدام أحجام السيارات من النظام", default=True,
    )
    use_system_tint_grades = fields.Boolean(
        string="استخدام جميع درجات اللون من النظام", default=True,
        help="عند التفعيل يستخدم الفيلم جميع درجات اللون المفعلة في مركز تهيئة النظام.",
    )
    car_size_ids = fields.Many2many(
        'wof.car.size', 'wof_film_category_car_size_rel',
        'film_id', 'size_id', string="أحجام السيارات",
        domain="[('company_id', '=', company_id), ('active', '=', True)]",
        check_company=True,
    )
    use_system_commission_policy = fields.Boolean(
        string="استخدام سياسة عمولة النظام", default=True,
    )
    commission_event = fields.Selection(
        [('delivery', 'بعد إنجاز أمر التركيب'),
         ('invoice', 'بعد ترحيل الفاتورة')],
        string="سياسة استحقاق العمولة", default='delivery', required=True,
    )
    commission_calculation_policy = fields.Selection(
        [('fixed', 'عمولة موحدة'), ('by_size', 'حسب حجم السيارة')],
        string="طريقة احتساب العمولة", default='fixed', required=True,
        help="يحدد شكل إدخال العمولة في خطوة الأسعار والعمولات: قيمة/نسبة موحدة أو قيمة/نسبة مستقلة لكل حجم سيارة.",
    )
    use_system_tax_policy = fields.Boolean(
        string="استخدام السياسة الضريبية من النظام", default=True,
        help="عند التفعيل يرث الفيلم/الخدمة إعداد الضريبة وطريقة إدخال السعر من مركز تهيئة النظام.",
    )
    tax_enabled = fields.Boolean(
        string="تطبيق الضريبة", default=True,
    )
    tax_id = fields.Many2one(
        'account.tax', string="الضريبة", check_company=True,
        domain="[('type_tax_use', '=', 'sale'), ('company_id', '=', company_id)]",
    )
    price_input_mode = fields.Selection(
        [('excluded', 'السعر قبل الضريبة'), ('included', 'السعر شامل الضريبة')],
        string="طريقة إدخال السعر", default='excluded', required=True,
    )
    film_category_line_ids = fields.One2many(
        'wof.film.category.lines', 'header_id', string="درجات الفيلم والمنتجات",
    )
    film_part_line_ids = fields.One2many(
        'wof.film.parts.lines', 'header_id', string="الأجزاء والأسعار",
    )
    parts_count = fields.Integer(compute='_compute_counts')
    price_count = fields.Integer(compute='_compute_counts')
    commission_count = fields.Integer(compute='_compute_counts')
    grade_count = fields.Integer(compute='_compute_counts')
    pricing_summary = fields.Char(compute='_compute_configuration_summary')
    commission_summary = fields.Char(compute='_compute_configuration_summary')
    car_size_count = fields.Integer(compute='_compute_configuration_summary')
    configuration_ready = fields.Boolean(compute='_compute_configuration_summary')
    configuration_state = fields.Selection(
        [('ready', 'جاهز'), ('needs_setup', 'يحتاج إلى تهيئة')],
        compute='_compute_configuration_summary', string="حالة التهيئة",
    )
    configuration_note = fields.Char(compute='_compute_configuration_summary')

    _sql_constraints = [
        ('film_name_service_company_unique', 'unique(name, service_type_id, company_id)',
         'اسم الفيلم مستخدم مسبقًا لنفس الخدمة والشركة.'),
        ('film_code_company_unique', 'unique(code, company_id)',
         'كود الفيلم مستخدم مسبقًا في هذه الشركة.'),
        ('film_warranty_nonnegative', 'check(warranty_years >= 0)',
         'سنوات الضمان لا يمكن أن تكون سالبة.'),
    ]

    @api.depends(
        'film_part_line_ids.price_line_ids',
        'film_part_line_ids.commission_line_ids',
        'film_category_line_ids',
    )
    def _compute_counts(self):
        for record in self:
            record.parts_count = len(record.film_part_line_ids)
            record.price_count = sum(len(line.price_line_ids) for line in record.film_part_line_ids)
            record.commission_count = sum(
                len(line.commission_line_ids) for line in record.film_part_line_ids
            )
            record.grade_count = len(record.film_category_line_ids)

    @api.depends(
        'film_part_line_ids.price_line_ids.car_size_id',
        'film_part_line_ids.commission_line_ids.car_size_id',
    )
    def _compute_configuration_summary(self):
        for record in self:
            prices = record.film_part_line_ids.price_line_ids
            commissions = record.film_part_line_ids.commission_line_ids
            record.pricing_summary = record._mode_summary(prices)
            record.commission_summary = record._mode_summary(commissions)
            size_ids = prices.mapped('car_size_id').filtered(lambda size: size)
            record.car_size_count = len(size_ids)
            has_parts = bool(record.film_part_line_ids.filtered('part_selected'))
            has_prices = bool(prices)
            grades_ok = (not record.supports_color_grades) or bool(record.film_category_line_ids.filtered('active'))
            record.configuration_ready = bool(has_parts and has_prices and grades_ok)
            record.configuration_state = 'ready' if record.configuration_ready else 'needs_setup'
            missing = []
            if not has_parts:
                missing.append('المكونات')
            if not has_prices:
                missing.append('الأسعار')
            if not grades_ok:
                missing.append('درجات اللون')
            record.configuration_note = ('الإعداد مكتمل' if not missing else 'غير مكتمل: %s' % '، '.join(missing))

    @api.model
    def _mode_summary(self, lines):
        if not lines:
            return 'غير مكتمل'
        has_default = any(not line.car_size_id for line in lines)
        has_sizes = any(line.car_size_id for line in lines)
        if has_default and has_sizes:
            return 'سعر أساسي + حسب الحجم'
        return 'حسب حجم السيارة' if has_sizes else 'عام'

    @api.constrains('service_type_id')
    def _check_grades_match_activity(self):
        for record in self:
            if record.film_category_line_ids and not record.supports_color_grades:
                raise ValidationError(
                    'درجات اللون متاحة لخدمات العزل الحراري فقط.'
                )


    def action_configure(self):
        self.ensure_one()
        hub = self.env.context.get('wof_activity_hub_id')
        wizard = self.env['wof.film.setup.wizard'].create_for_activity(
            self.service_type_id,
            hub=self.env['wof.activity.hub'].browse(hub).exists() if hub else None,
            film=self,
        )
        return wizard._dialog_action()

    def action_create_component(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'إضافة مكوّن للخدمة',
            'res_model': 'wof.film.parts.lines',
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_header_id': self.id},
        }

    def action_open_components(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'مكوّنات %s' % self.display_name,
            'res_model': 'wof.film.parts.lines',
            'view_mode': 'tree,form',
            'domain': [('header_id', '=', self.id)],
            'context': {'default_header_id': self.id},
        }

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
    transmission_percent = fields.Integer(string="نسبة نفاذ الضوء %")
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
        ('film_grade_transmission_range',
         'check(transmission_percent >= 0 AND transmission_percent <= 100)',
         'نسبة نفاذ الضوء يجب أن تكون بين 0 و 100.'),
    ]

    @api.constrains('header_id')
    def _check_tint_activity_only(self):
        for record in self:
            if record.header_id and not record.header_id.supports_color_grades:
                raise ValidationError(
                    'لا يمكن إضافة درجة لون لخدمة خارج نشاط العزل الحراري.'
                )


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
    supports_color_grades = fields.Boolean(
        related='header_id.supports_color_grades', readonly=True,
    )
    company_id = fields.Many2one(
        related='header_id.company_id', store=True, readonly=True, index=True,
    )
    part_selected = fields.Boolean(string="مفعّل", default=True)
    car_part_id = fields.Many2one(
        'wof.car.parts', string="الجزء", required=True,
        ondelete='restrict', check_company=True, index=True,
    )
    part_type = fields.Selection(
        related='car_part_id.part_type', readonly=True, string='نوع المكوّن',
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
    service_commission_source = fields.Selection(
        [('independent', 'عمولة منطقة الخدمة'), ('from_parts', 'عمولة من مكونات الخدمة')],
        string="مصدر عمولة منطقة الخدمة", default='independent', required=True,
        help="يستخدم فقط عندما يكون المكوّن منطقة خدمة. في وضع حسب المكونات تُشتق عمولة المنطقة من أجزائها.",
    )
    commission_calculation_policy = fields.Selection(
        [('fixed', 'عمولة موحدة'), ('by_size', 'حسب حجم السيارة')],
        string="طريقة احتساب عمولة المكوّن",
        help="إذا لم تُحدد، تستخدم سياسة العمولة العامة للفيلم. يمكن تخصيصها لكل مكوّن من شاشة تفاصيل العمولة.",
    )
    commission_value_type = fields.Selection(
        [('fixed', 'مبلغ ثابت'), ('percent', 'نسبة مئوية')],
        string="نوع العمولة", default='fixed', required=True,
        help="يحدد ما إذا كانت قيمة العمولة مبلغًا ثابتًا أو نسبة مئوية من سعر المكوّن المهيأ.",
    )
    commission_readonly = fields.Boolean(
        string="العمولة للقراءة فقط",
        help="عند التفعيل تعتبر عمولة هذا المكوّن ثابتة ولا يسمح بتجاوزها تشغيليًا.",
    )
    technician_commission_distribution = fields.Selection(
        [('equal', 'بالتساوي بين الفنيين'),
         ('by_technician_ratio', 'حسب نسبة الفني'),
         ('by_part', 'حسب عمولة الجزء المنفذ')],
        string="طريقة توزيع عمولة الفنيين", default='equal', required=True,
        help="حسب نسبة الفني تستخدم النسبة المعرفة في بطاقة الموظف للفني. خيار حسب الجزء مخصص لمناطق الخدمة.",
    )
    price_count = fields.Integer(compute='_compute_counts')
    commission_count = fields.Integer(compute='_compute_counts')
    price_mode = fields.Selection(
        [('missing', 'غير مكتمل'), ('default', 'سعر عام'),
         ('size', 'حسب الحجم'), ('mixed', 'أساسي + حسب الحجم')],
        compute='_compute_counts', string="سياسة السعر",
    )
    commission_mode = fields.Selection(
        [('missing', 'غير مكتمل'), ('default', 'عمولة عامة'),
         ('size', 'حسب الحجم'), ('mixed', 'أساسية + حسب الحجم')],
        compute='_compute_counts', string="سياسة العمولة",
    )

    _sql_constraints = [
        ('film_part_unique', 'unique(car_part_id, header_id)',
         'هذا الجزء موجود مسبقًا لنفس الفيلم.'),
    ]

    @api.depends('price_line_ids', 'commission_line_ids')
    def _compute_counts(self):
        for record in self:
            record.price_count = len(record.price_line_ids)
            record.commission_count = len(record.commission_line_ids)
            record.price_mode = record._line_mode(record.price_line_ids)
            record.commission_mode = record._line_mode(record.commission_line_ids)

    @api.model
    def _line_mode(self, lines):
        if not lines:
            return 'missing'
        has_default = any(not line.car_size_id for line in lines)
        has_sizes = any(line.car_size_id for line in lines)
        if has_default and has_sizes:
            return 'mixed'
        return 'size' if has_sizes else 'default'

    @api.constrains('header_id', 'film_category_line_id')
    def _check_default_grade(self):
        for record in self:
            grade = record.film_category_line_id
            if grade and not record.header_id.supports_color_grades:
                raise ValidationError(
                    'الدرجة الافتراضية متاحة لمكوّنات العزل الحراري فقط.'
                )
            if grade and grade.header_id != record.header_id:
                raise ValidationError(
                    'الدرجة الافتراضية يجب أن تتبع الخدمة / الفيلم نفسه.'
                )

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
        'wof.film.parts.lines', string="مكوّن الخدمة", required=True,
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
                record.price_readonly = False

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
        'wof.film.parts.lines', string="مكوّن الخدمة", required=True,
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
        string="قيمة العمولة", currency_field='currency_id',
        help="تُفسر كمبلغ أو كنسبة مئوية وفق نوع العمولة في المكوّن.",
    )
    commission_value_type = fields.Selection(
        related='part_line_id.commission_value_type', store=True, readonly=True,
        string="نوع العمولة",
    )

    _sql_constraints = [
        ('film_part_commission_size_unique', 'unique(part_line_id, car_size_id)',
         'عمولة هذا الحجم مضافة مسبقًا لهذا الجزء.'),
        ('film_part_commission_nonnegative', 'check(commission >= 0)',
         'العمولة لا يمكن أن تكون سالبة.'),
    ]

    @api.constrains('commission', 'part_line_id')
    def _check_percentage_commission_range(self):
        for record in self:
            if (
                record.part_line_id.commission_value_type == 'percent'
                and (record.commission < 0 or record.commission > 100)
            ):
                raise ValidationError('نسبة العمولة يجب أن تكون بين 0 و100.')

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
