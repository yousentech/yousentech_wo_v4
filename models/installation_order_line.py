# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

from .installation_order import (
    ORDER_LINE_INTERNAL_TOKEN,
    ORDER_PARENT_CREATE_TOKEN,
)


class WofInstallationOrderLine(models.Model):
    _name = 'wof.installation.order.line'
    _inherit = ['wof.api.mixin']
    _description = 'خدمة في أمر تركيب'
    _order = 'sequence, id'
    _check_company_auto = True

    sequence = fields.Integer(default=10)
    order_id = fields.Many2one(
        'wof.installation.order', string="أمر التركيب", required=True,
        ondelete='cascade', check_company=True, index=True,
    )
    company_id = fields.Many2one(
        related='order_id.company_id', store=True, readonly=True, index=True,
    )
    currency_id = fields.Many2one(
        related='order_id.currency_id', store=True, readonly=True,
    )
    car_size_id = fields.Many2one(
        related='order_id.car_size_id', store=True, readonly=True,
    )
    order_state = fields.Selection(
        related='order_id.state', store=True, readonly=True,
    )
    available_technician_ids = fields.Many2many(
        related='order_id.technician_ids', readonly=True,
    )
    available_car_part_ids = fields.Many2many(
        'wof.car.parts', compute='_compute_available_configuration',
        string="مكوّنات الخدمة المتاحة",
    )
    available_grade_ids = fields.Many2many(
        'wof.film.category.lines', compute='_compute_available_configuration',
        string="درجات لون الخدمة",
    )
    service_type_id = fields.Many2one(
        'wof.service.type', string="نشاط المركز", required=True,
        ondelete='restrict', check_company=True, index=True,
    )
    film_category_id = fields.Many2one(
        'wof.film.category', string="الخدمة / الفيلم", required=True,
        ondelete='restrict', check_company=True, index=True,
        domain="[('service_type_id', '=', service_type_id), ('company_id', '=', company_id)]",
    )
    supports_color_grades = fields.Boolean(
        related='film_category_id.supports_color_grades', readonly=True,
    )
    film_category_line_id = fields.Many2one(
        'wof.film.category.lines', string="درجة لون العزل",
        ondelete='restrict', check_company=True,
        domain="[('id', 'in', available_grade_ids)]",
    )
    car_part_id = fields.Many2one(
        'wof.car.parts', string="مكوّن الخدمة", required=True,
        ondelete='restrict', check_company=True, index=True,
        domain="[('id', 'in', available_car_part_ids)]",
    )
    service_product_id = fields.Many2one(
        related='car_part_id.product_id', store=True, readonly=True,
    )
    film_product_id = fields.Many2one(
        'product.product', string="منتج الفيلم",
        ondelete='restrict', check_company=True,
    )
    quantity = fields.Float(string="الكمية", required=True, default=1.0)

    price_source = fields.Selection(
        [
            ('size', 'سعر حجم السيارة'),
            ('default', 'السعر الأساسي'),
            ('manual', 'تجاوز يدوي معتمد'),
        ],
        string="مصدر السعر", readonly=True, copy=False,
    )
    price_source_note = fields.Char(
        string="تفسير السعر", readonly=True, copy=False,
    )
    unit_price = fields.Monetary(
        string="سعر الوحدة", currency_field='currency_id',
        readonly=True, copy=False,
    )
    configured_unit_price = fields.Monetary(
        string="السعر المهيأ", currency_field='currency_id',
        readonly=True, copy=False,
    )
    tax_id = fields.Many2one(
        'account.tax', string="الضريبة", readonly=True, copy=False,
        ondelete='restrict', check_company=True,
        domain=[('type_tax_use', '=', 'sale')],
    )
    max_discount_percent = fields.Float(
        string="حد الخصم المهيأ", readonly=True, copy=False,
    )
    configured_commission = fields.Monetary(
        string="عمولة الفني المهيأة", currency_field='currency_id',
        readonly=True, copy=False,
    )
    use_manual_price = fields.Boolean(
        string="استخدام سعر استثنائي", copy=False,
    )
    manual_unit_price = fields.Monetary(
        string="السعر الاستثنائي", currency_field='currency_id', copy=False,
    )
    price_override_reason = fields.Char(
        string="سبب تجاوز السعر", copy=False,
    )
    discount_type = fields.Selection(
        [('percent', 'نسبة'), ('amount', 'مبلغ')],
        string="نوع الخصم", default='percent', required=True,
    )
    discount_value = fields.Float(string="قيمة الخصم", default=0.0)
    discount_scope = fields.Selection(
        related='order_id.discount_scope', store=True, readonly=True,
    )
    discount_amount = fields.Monetary(
        string="الخصم", currency_field='currency_id',
        compute='_compute_line_amounts', store=True,
    )
    amount_untaxed = fields.Monetary(
        string="قبل الضريبة", currency_field='currency_id',
        compute='_compute_line_amounts', store=True,
    )
    amount_tax = fields.Monetary(
        string="قيمة الضريبة", currency_field='currency_id',
        compute='_compute_line_amounts', store=True,
    )
    amount_total = fields.Monetary(
        string="الإجمالي", currency_field='currency_id',
        compute='_compute_line_amounts', store=True,
    )

    execution_technician_id = fields.Many2one(
        'res.users', string="فني التنفيذ", ondelete='restrict',
    )
    execution_progress = fields.Integer(
        string="الإنجاز %", default=0, copy=False,
    )
    execution_notes = fields.Char(string="ملاحظات التنفيذ", copy=False)

    _sql_constraints = [
        (
            'installation_order_line_unique',
            'unique(order_id, film_category_id, car_part_id)',
            'هذا الجزء مضاف مسبقًا لنفس الفيلم في أمر التركيب.',
        ),
        (
            'installation_order_line_quantity_positive',
            'check(quantity > 0)',
            'كمية الخدمة يجب أن تكون أكبر من صفر.',
        ),
        (
            'installation_order_line_discount_nonnegative',
            'check(discount_value >= 0)',
            'قيمة الخصم لا يمكن أن تكون سالبة.',
        ),
        (
            'installation_order_line_progress_range',
            'check(execution_progress >= 0 AND execution_progress <= 100)',
            'نسبة الإنجاز يجب أن تكون بين 0 و100.',
        ),
        (
            'installation_order_line_manual_price_nonnegative',
            'check(manual_unit_price >= 0)',
            'السعر الاستثنائي لا يمكن أن يكون سالبًا.',
        ),
    ]

    @api.depends(
        'film_category_id',
        'film_category_id.film_part_line_ids.part_selected',
        'film_category_id.film_part_line_ids.car_part_id',
        'film_category_id.film_category_line_ids.active',
    )
    def _compute_available_configuration(self):
        for line in self:
            service = line.film_category_id
            line.available_car_part_ids = service.film_part_line_ids.filtered(
                'part_selected'
            ).car_part_id
            line.available_grade_ids = (
                service.film_category_line_ids.filtered('active')
                if service.supports_color_grades
                else self.env['wof.film.category.lines']
            )

    @api.model
    def resolve_default_grade_id(self, film_category_id, car_part_id, company_id):
        """Resolve the configured tint grade for Odoo and future API callers."""
        if not film_category_id or not car_part_id or not company_id:
            return False
        part_line = self.env['wof.film.parts.lines'].search([
            ('header_id', '=', film_category_id),
            ('car_part_id', '=', car_part_id),
            ('company_id', '=', company_id),
            ('part_selected', '=', True),
        ], limit=1)
        if not part_line or not part_line.header_id.supports_color_grades:
            return False
        if part_line.film_category_line_id.active:
            return part_line.film_category_line_id.id
        grades = part_line.header_id.film_category_line_ids.filtered('active')
        return grades.id if len(grades) == 1 else False

    @api.depends(
        'quantity',
        'unit_price',
        'discount_type',
        'discount_value',
        'tax_id',
        'currency_id',
        'order_id.partner_id',
        'order_id.discount_scope',
        'order_id.order_discount_percent',
    )
    def _compute_line_amounts(self):
        for line in self:
            gross = line.unit_price * line.quantity
            discount = (
                gross * line.order_id.order_discount_percent / 100.0
                if line.discount_scope == 'order'
                else (
                    gross * line.discount_value / 100.0
                    if line.discount_type == 'percent'
                    else line.discount_value
                )
            )
            line.discount_amount = discount
            discounted_unit = (
                (gross - discount) / line.quantity
                if line.quantity
                else 0.0
            )
            taxes = line.tax_id.compute_all(
                discounted_unit,
                currency=line.currency_id,
                quantity=line.quantity,
                product=line.service_product_id,
                partner=line.order_id.partner_id,
            ) if line.tax_id else {
                'total_excluded': gross - discount,
                'total_included': gross - discount,
            }
            line.amount_untaxed = taxes['total_excluded']
            line.amount_tax = taxes['total_included'] - taxes['total_excluded']
            line.amount_total = taxes['total_included']

    @api.constrains(
        'discount_type',
        'discount_value',
        'unit_price',
        'quantity',
        'max_discount_percent',
    )
    def _check_discount(self):
        for line in self:
            gross = line.unit_price * line.quantity
            if line.discount_scope == 'order' and line.discount_value:
                raise ValidationError(
                    'خصم هذا الفرع يطبق على إجمالي الأمر؛ لا تضف خصمًا داخل الخدمة.'
                )
            if line.discount_type == 'percent' and line.discount_value > 100:
                raise ValidationError('نسبة الخصم لا يمكن أن تتجاوز 100٪.')
            if line.discount_type == 'amount' and line.discount_value > gross:
                raise ValidationError(
                    'مبلغ الخصم لا يمكن أن يتجاوز إجمالي الخدمة.'
                )
            actual_percent = (
                (line.order_id.order_discount_percent if gross else 0.0)
                if line.discount_scope == 'order'
                else (
                    line.discount_value
                    if line.discount_type == 'percent'
                    else (line.discount_value / gross * 100.0 if gross else 0.0)
                )
            )
            if actual_percent > line.max_discount_percent:
                raise ValidationError(
                    'الخصم يتجاوز الحد المهيأ لهذه الخدمة (%s٪).'
                    % line.max_discount_percent
                )

    @api.constrains('company_id', 'execution_technician_id')
    def _check_execution_technician_company(self):
        for line in self:
            if (
                line.execution_technician_id
                and line.company_id not in line.execution_technician_id.company_ids
            ):
                raise ValidationError(
                    'فني التنفيذ غير مسموح له بالعمل في فرع الأمر.'
                )
            if (
                line.execution_technician_id
                and line.execution_technician_id not in line.available_technician_ids
            ):
                raise ValidationError(
                    'فني تنفيذ الخدمة يجب أن يكون ضمن فنيي أمر التركيب.'
                )

    @api.onchange('service_type_id')
    def _onchange_service_type_id(self):
        self.film_category_id = False
        self.film_category_line_id = False
        self.car_part_id = False
        if self.service_type_id and self.company_id:
            films = self.env['wof.film.category'].search([
                ('service_type_id', '=', self.service_type_id.id),
                ('company_id', '=', self.company_id.id),
                ('active', '=', True),
            ], limit=2)
            if len(films) == 1:
                self.film_category_id = films

    @api.onchange('film_category_id')
    def _onchange_film_category_id(self):
        self.film_category_line_id = False
        self.car_part_id = False
        if self.film_category_id:
            parts = self.film_category_id.film_part_line_ids.filtered(
                'part_selected'
            )
            if len(parts) == 1:
                self.car_part_id = parts.car_part_id
                self._onchange_car_part_id()

    @api.onchange('car_part_id')
    def _onchange_car_part_id(self):
        self.film_category_line_id = False
        if self.film_category_id and self.car_part_id:
            grade_id = self.resolve_default_grade_id(
                self.film_category_id.id,
                self.car_part_id.id,
                self.company_id.id,
            )
            self.film_category_line_id = grade_id

    @api.constrains(
        'service_type_id',
        'film_category_id',
        'film_category_line_id',
        'car_part_id',
    )
    def _check_configuration_relations(self):
        for line in self:
            if line.film_category_id.service_type_id != line.service_type_id:
                raise ValidationError(
                    'الفيلم المختار لا يتبع الخدمة المحددة.'
                )
            if (
                line.film_category_line_id
                and line.film_category_line_id.header_id
                != line.film_category_id
            ):
                raise ValidationError(
                    'درجة الفيلم المختارة لا تتبع الفيلم المحدد.'
                )
            if line.film_category_line_id and not line.supports_color_grades:
                raise ValidationError(
                    'درجات اللون متاحة لخدمات العزل الحراري فقط.'
                )
            configured_part = self.env['wof.film.parts.lines'].search_count([
                ('header_id', '=', line.film_category_id.id),
                ('car_part_id', '=', line.car_part_id.id),
                ('company_id', '=', line.company_id.id),
                ('part_selected', '=', True),
            ])
            if not configured_part:
                raise ValidationError(
                    'مكوّن الخدمة المختار غير مرتبط بهذه الخدمة / الفيلم.'
                )

    @api.model_create_multi
    def create(self, vals_list):
        records = self.browse()
        for incoming in vals_list:
            vals = dict(incoming)
            pending_discount = {
                'discount_type': vals.pop('discount_type', 'percent'),
                'discount_value': vals.pop('discount_value', 0.0),
            }
            order = self.env['wof.installation.order'].browse(
                vals.get('order_id')
            ).exists()
            if not order:
                raise ValidationError('يجب تحديد أمر التركيب للخدمة.')
            self._ensure_commercial_editor(order)
            if order.state not in {'draft', 'scheduled'}:
                raise ValidationError(
                    'لا يمكن إضافة خدمة بعد إكمال استلام السيارة.'
                )
            for protected in (
                'company_id',
                'discount_scope',
                'unit_price',
                'configured_unit_price',
                'price_source',
                'price_source_note',
                'tax_id',
                'max_discount_percent',
                'configured_commission',
                'execution_technician_id',
                'execution_progress',
                'execution_notes',
            ):
                vals.pop(protected, None)
            vals['execution_progress'] = 0
            if not vals.get('film_category_line_id'):
                vals['film_category_line_id'] = self.resolve_default_grade_id(
                    vals.get('film_category_id'),
                    vals.get('car_part_id'),
                    order.company_id.id,
                )
            vals.update({
                'discount_type': 'percent',
                'discount_value': 0.0,
                'max_discount_percent': 100.0,
            })
            record = super(
                WofInstallationOrderLine,
                self
            ).create([vals])
            record._refresh_pricing()
            if (
                pending_discount['discount_type'] != 'percent'
                or pending_discount['discount_value']
            ):
                record.write(pending_discount)
            if (
                record.use_manual_price
                and self.env.context.get('wof_order_parent_create_token')
                is not ORDER_PARENT_CREATE_TOKEN
            ):
                record.order_id._log_business_event(
                    'order.price_overridden',
                    note=record.price_override_reason,
                    details={
                        'line_uuid': record.public_uuid,
                        'activity_code': record.service_type_id.code,
                        'service_code': record.film_category_id.code,
                        'part_code': record.car_part_id.code,
                        'old_price': record.configured_unit_price,
                        'configured_price': record.configured_unit_price,
                        'new_price': record.unit_price,
                        'currency': record.currency_id.name,
                    },
                )
            records |= record
        return records

    def write(self, vals):
        vals = dict(vals)
        relation_change = {'film_category_id', 'car_part_id'}.intersection(vals)
        if relation_change and 'film_category_line_id' not in vals and len(self) > 1:
            for line in self:
                line.write(vals)
            return True
        if relation_change and 'film_category_line_id' not in vals and self:
            line = self.ensure_one()
            vals['film_category_line_id'] = self.resolve_default_grade_id(
                vals.get('film_category_id', line.film_category_id.id),
                vals.get('car_part_id', line.car_part_id.id),
                line.company_id.id,
            )
        protected = {
            'order_id',
            'company_id',
            'currency_id',
            'car_size_id',
            'unit_price',
            'configured_unit_price',
            'price_source',
            'price_source_note',
            'tax_id',
            'max_discount_percent',
            'configured_commission',
        }
        internal = (
            self.env.context.get('wof_order_line_internal_token')
            is ORDER_LINE_INTERNAL_TOKEN
        )
        if protected.intersection(vals) and not internal:
            raise ValidationError(
                'السعر ومصدره والضريبة تحددها خدمة التسعير ولا تعدل مباشرة.'
            )
        commercial = {
            'service_type_id',
            'film_category_id',
            'film_category_line_id',
            'car_part_id',
            'film_product_id',
            'quantity',
            'discount_type',
            'discount_value',
            'use_manual_price',
            'manual_unit_price',
            'price_override_reason',
        }
        execution = {
            'execution_technician_id',
            'execution_progress',
            'execution_notes',
        }
        needs_refresh = bool(
            {
                'service_type_id',
                'film_category_id',
                'film_category_line_id',
                'car_part_id',
                'use_manual_price',
                'manual_unit_price',
                'price_override_reason',
            }.intersection(vals)
        )
        if not internal:
            for line in self:
                if commercial.intersection(vals):
                    self._ensure_commercial_editor(line.order_id)
                    if line.order_id.state not in {'draft', 'scheduled'}:
                        raise ValidationError(
                            'لا يمكن تعديل الخدمة أو سعرها بعد إكمال الاستلام.'
                        )
                if execution.intersection(vals):
                    self._ensure_execution_editor(line.order_id)
                    if line.order_id.state != 'in_progress':
                        raise ValidationError(
                            'تحديث فني الخدمة أو تقدمها متاح أثناء التنفيذ فقط.'
                        )
                    is_supervisor = any(
                        self.env.user.has_group(group)
                        for group in (
                            'yousentech_wo_v4.group_wo_supervisor',
                            'yousentech_wo_v4.group_wo_manager',
                        )
                    )
                    if not is_supervisor:
                        target_user_id = vals.get(
                            'execution_technician_id',
                            line.execution_technician_id.id,
                        )
                        if (
                            line.execution_technician_id
                            and line.execution_technician_id != self.env.user
                        ) or (
                            target_user_id
                            and target_user_id != self.env.user.id
                        ):
                            raise AccessError(
                                'يمكن للفني تحديث الخدمات المسندة إليه فقط.'
                            )
        before_manual = {
            line.id: (line.price_source, line.unit_price)
            for line in self
        }
        result = super().write(vals)
        if needs_refresh and not internal:
            self._refresh_pricing()
            for line in self.filtered('use_manual_price'):
                old_source, old_price = before_manual[line.id]
                if old_source != 'manual' or old_price != line.unit_price:
                    line.order_id._log_business_event(
                        'order.price_overridden',
                        note=line.price_override_reason,
                        details={
                            'line_uuid': line.public_uuid,
                            'activity_code': line.service_type_id.code,
                            'service_code': line.film_category_id.code,
                            'part_code': line.car_part_id.code,
                            'old_price': old_price,
                            'new_price': line.unit_price,
                            'currency': line.currency_id.name,
                        },
                    )
        return result

    def unlink(self):
        for line in self:
            self._ensure_commercial_editor(line.order_id)
            if line.order_id.state not in {'draft', 'scheduled'}:
                raise ValidationError(
                    'لا يمكن حذف خدمة بعد إكمال استلام السيارة.'
                )
        return super().unlink()

    @api.model
    def _ensure_commercial_editor(self, order):
        if not any(
            self.env.user.has_group(group)
            for group in (
                'yousentech_wo_v4.group_wo_user',
                'yousentech_wo_v4.group_wo_supervisor',
                'yousentech_wo_v4.group_wo_manager',
            )
        ):
            raise AccessError(
                'تعديل خدمات وتسعير الأمر متاح للاستقبال أو المشرف أو مدير المركز.'
            )

    @api.model
    def _ensure_execution_editor(self, order):
        if not any(
            self.env.user.has_group(group)
            for group in (
                'yousentech_wo_v4.group_wo_technician',
                'yousentech_wo_v4.group_wo_supervisor',
                'yousentech_wo_v4.group_wo_manager',
            )
        ):
            raise AccessError(
                'تحديث التنفيذ متاح للفني أو المشرف أو مدير المركز.'
            )

    def _write_line_internal(self, values):
        if not self:
            return True
        return self.with_context(
            wof_order_line_internal_token=ORDER_LINE_INTERNAL_TOKEN
        ).write(values)

    def _pricing_configuration(self):
        self.ensure_one()
        part_line = self.env['wof.film.parts.lines'].search([
            ('header_id', '=', self.film_category_id.id),
            ('service_type_id', '=', self.service_type_id.id),
            ('car_part_id', '=', self.car_part_id.id),
            ('part_selected', '=', True),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not part_line:
            raise ValidationError(
                'الجزء «%s» غير مهيأ للفيلم «%s» ضمن الخدمة «%s». '
                'أضفه من مركز الإعدادات ثم أعد المحاولة.'
                % (
                    self.car_part_id.display_name,
                    self.film_category_id.display_name,
                    self.service_type_id.display_name,
                )
            )
        price = self.env['wof.film.parts.price.lines'].search([
            ('part_line_id', '=', part_line.id),
            ('car_size_id', '=', self.car_size_id.id),
        ], limit=1)
        source = 'size'
        if not price:
            price = self.env['wof.film.parts.price.lines'].search([
                ('part_line_id', '=', part_line.id),
                ('car_size_id', '=', False),
            ], limit=1)
            source = 'default'
        if not price:
            raise ValidationError(
                'لا يوجد سعر مهيأ للجزء «%s» بحجم السيارة «%s»، '
                'ولا يوجد سعر أساسي بديل. أضف السعر من مركز الإعدادات.'
                % (
                    self.car_part_id.display_name,
                    self.car_size_id.display_name,
                )
            )
        commission = self.env['wof.film.parts.commission.lines'].search([
            ('part_line_id', '=', part_line.id),
            ('car_size_id', '=', self.car_size_id.id),
        ], limit=1)
        if not commission:
            commission = self.env['wof.film.parts.commission.lines'].search([
                ('part_line_id', '=', part_line.id),
                ('car_size_id', '=', False),
            ], limit=1)
        return part_line, price, commission, source

    def _refresh_pricing(self):
        for line in self:
            if line.use_manual_price:
                if not self.env.user.has_group(
                    'yousentech_wo_v4.group_wo_price_override'
                ):
                    raise AccessError(
                        'تجاوز السعر متاح فقط للمستخدم المخول بذلك.'
                    )
                reason = (line.price_override_reason or '').strip()
                if not reason:
                    raise ValidationError(
                        'اكتب سبب تجاوز السعر قبل تطبيق السعر الاستثنائي.'
                    )
                part_line, price, commission, source = line._pricing_configuration()
                if price.free_part:
                    raise ValidationError('هذا السعر محدد كمجاني في تهيئة الفيلم ولا يمكن تجاوزه يدويًا.')
                if price.price_readonly:
                    raise ValidationError('هذا السعر محدد للقراءة فقط في تهيئة الفيلم ولا يمكن تجاوزه يدويًا.')
                line._write_line_internal({
                    'unit_price': line.manual_unit_price,
                    'configured_unit_price': price.part_price,
                    'price_source': 'manual',
                    'price_source_note': 'سعر استثنائي معتمد: %s' % reason,
                    'tax_id': price.tax_id.id if price.tax_id else False,
                    'max_discount_percent': price.discount_exceed_limit,
                    'configured_commission': commission.commission if commission else 0.0,
                })
                continue
            part_line, price, commission, source = line._pricing_configuration()
            if price.free_part:
                note = 'خدمة مجانية وفق تهيئة الجزء'
            elif source == 'size':
                note = 'سعر مهيأ لحجم السيارة: %s' % line.car_size_id.display_name
            else:
                note = 'السعر الأساسي لأن هذا الحجم لا يملك سعرًا خاصًا'
            values = {
                'unit_price': price.part_price,
                'configured_unit_price': price.part_price,
                'price_source': source,
                'price_source_note': note,
                'tax_id': price.tax_id.id if price.tax_id else False,
                'max_discount_percent': price.discount_exceed_limit,
                'configured_commission': commission.commission if commission else 0.0,
            }
            if not line.film_product_id and line.film_category_line_id.product_id:
                values['film_product_id'] = line.film_category_line_id.product_id.id
            line._write_line_internal(values)
        return True

    def _validate_ready_for_confirmation(self):
        for line in self:
            if not line.price_source:
                line._refresh_pricing()
            if line.use_manual_price and not line.price_override_reason:
                raise ValidationError(
                    'السعر الاستثنائي يحتاج سببًا واضحًا قبل تأكيد الأمر.'
                )
        return True

    def action_refresh_price(self):
        for line in self:
            self._ensure_commercial_editor(line.order_id)
            if line.order_id.state not in {'draft', 'scheduled'}:
                raise ValidationError(
                    'إعادة احتساب السعر متاحة قبل إكمال استلام السيارة فقط.'
                )
        self._refresh_pricing()
        return True
