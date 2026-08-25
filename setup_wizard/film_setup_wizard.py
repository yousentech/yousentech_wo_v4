# -*- coding: utf-8 -*-

import re
from datetime import datetime

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class WofFilmSetupWizard(models.TransientModel):
    _name = 'wof.film.setup.wizard'
    _description = 'معالج تهيئة فيلم أو خدمة'

    hub_id = fields.Many2one('wof.activity.hub', string='بوابة الأنشطة', readonly=True)
    profile_id = fields.Many2one('wof.company.profile', string='مركز التهيئة', required=True, readonly=True)
    company_id = fields.Many2one('res.company', string='الشركة', required=True, readonly=True)
    activity_id = fields.Many2one(
        'wof.service.type', string='النشاط', required=True, readonly=True,
        domain="[('company_id', '=', company_id), ('active', '=', True)]",
    )
    film_id = fields.Many2one('wof.film.category', string='الفيلم / الخدمة', readonly=True)
    mode = fields.Selection([('create', 'إضافة'), ('edit', 'تعديل')], default='create', required=True, readonly=True)
    current_step = fields.Selection(
        [('basic', 'البيانات الأساسية'), ('tint', 'درجات اللون'),
         ('components', 'المكونات'), ('pricing', 'الأسعار والعمولات'),
         ('review', 'المراجعة والتفعيل')],
        default='basic', required=True, readonly=True,
    )

    # Stage 1 — basic information.
    item_type = fields.Selection(
        [('film', 'فيلم'), ('service', 'خدمة')], string='نوع العنصر', default='film', required=True,
    )
    name = fields.Char(string='اسم الفيلم / الخدمة')
    code = fields.Char(string='الكود')
    description = fields.Text(string='الوصف المختصر')
    active = fields.Boolean(string='مفعّل', default=True)
    warranty_years = fields.Integer(string='سنوات الضمان', default=5)
    inventory_enabled = fields.Boolean(string='يصرف مواد من المخزون')
    product_required = fields.Boolean(string='اختيار المنتج المخزني إلزامي')
    warning_msg = fields.Char(string='رسالة تنبيه')

    # Inherited policies / per-film overrides.
    use_system_pricing_policy = fields.Boolean(string='استخدام سياسة تسعير النظام', default=True)
    pricing_policy = fields.Selection(
        [('fixed', 'سعر موحد'), ('by_size', 'حسب حجم السيارة')],
        string='سياسة التسعير', default='fixed', required=True,
    )
    system_pricing_policy = fields.Selection(
        [('fixed', 'سعر موحد'), ('by_size', 'حسب حجم السيارة')],
        string='سياسة التسعير من النظام', readonly=True,
    )
    commission_calculation_policy = fields.Selection(
        [('fixed', 'عمولة موحدة'), ('by_size', 'حسب حجم السيارة')],
        string='طريقة احتساب العمولة', default='fixed', required=True,
    )

    use_system_car_sizes = fields.Boolean(string='استخدام أحجام النظام', default=True)
    car_size_ids = fields.Many2many(
        'wof.car.size', 'wof_film_setup_wizard_car_size_rel', 'wizard_id', 'size_id',
        string='أحجام السيارات',
        domain="[('company_id', '=', company_id), ('active', '=', True)]",
    )
    system_car_size_ids = fields.Many2many(
        'wof.car.size', 'wof_film_setup_wizard_system_size_rel', 'wizard_id', 'size_id',
        string='أحجام النظام', readonly=True,
    )

    use_system_commission_policy = fields.Boolean(string='استخدام سياسة عمولة النظام', default=True)
    commission_event = fields.Selection(
        [('delivery', 'بعد إنجاز أمر التركيب'), ('invoice', 'بعد ترحيل الفاتورة')],
        string='سياسة استحقاق العمولة', default='delivery', required=True,
    )
    system_commission_event = fields.Selection(
        [('delivery', 'بعد إنجاز أمر التركيب'), ('invoice', 'بعد ترحيل الفاتورة')],
        string='سياسة العمولة من النظام', readonly=True,
    )

    # Tax policy is inherited from the company setup in Stage 1.
    # We expose it here so the user sees all five policy groups without
    # duplicating tax configuration on the film record.
    system_tax_enabled = fields.Boolean(string='تطبيق الضريبة من النظام', readonly=True)
    system_tax_id = fields.Many2one('account.tax', string='الضريبة الافتراضية من النظام', readonly=True)
    system_price_input_mode = fields.Selection(
        [('excluded', 'السعر قبل الضريبة'), ('included', 'السعر شامل الضريبة')],
        string='طريقة إدخال السعر من النظام', readonly=True,
    )

    system_inventory_enabled = fields.Boolean(string='المخزون مفعل في النظام', readonly=True)
    system_tint_count = fields.Integer(string='درجات اللون في النظام', readonly=True)
    system_size_count = fields.Integer(string='أحجام السيارات في النظام', readonly=True)
    activity_film_count = fields.Integer(string='أفلام / خدمات النشاط', compute='_compute_activity_summary')
    activity_parts_count = fields.Integer(string='مكونات النشاط', compute='_compute_activity_summary')
    supports_color_grades = fields.Boolean(related='activity_id.supports_color_grades', readonly=True)
    activity_description = fields.Text(related='activity_id.description', readonly=True)

    @api.depends('activity_id')
    def _compute_activity_summary(self):
        Film = self.env['wof.film.category'].with_context(active_test=False)
        for wizard in self:
            if not wizard.activity_id:
                wizard.activity_film_count = 0
                wizard.activity_parts_count = 0
                continue
            films = Film.search([
                ('company_id', '=', wizard.company_id.id),
                ('service_type_id', '=', wizard.activity_id.id),
            ])
            wizard.activity_film_count = len(films)
            wizard.activity_parts_count = sum(films.mapped('parts_count'))

    def _ensure_access(self):
        self.ensure_one()
        if self.company_id not in self.env.companies:
            raise AccessError(_('لا يمكنك تهيئة فيلم أو خدمة لشركة غير مسموحة.'))
        if self.activity_id.company_id != self.company_id or not self.activity_id.active:
            raise ValidationError(_('النشاط المحدد غير متاح لهذه الشركة.'))
        return True

    @api.model
    def create_for_activity(self, activity, hub=None, film=None):
        activity.ensure_one()
        company = activity.company_id
        profile = self.env['wof.company.profile'].search([('company_id', '=', company.id)], limit=1)
        if not profile:
            raise ValidationError(_('لم يتم العثور على ملف تهيئة الشركة.'))

        active_sizes = self.env['wof.car.size'].search([
            ('company_id', '=', company.id), ('active', '=', True)
        ], order='name')
        selected_shades = profile.tint_shade_line_ids.filtered('selected')
        vals = {
            'hub_id': hub.id if hub else False,
            'profile_id': profile.id,
            'company_id': company.id,
            'activity_id': activity.id,
            'mode': 'edit' if film else 'create',
            'film_id': film.id if film else False,
            'current_step': 'basic',
            'system_pricing_policy': profile.operation_pricing_policy,
            'system_commission_event': profile.commission_event,
            'system_tax_enabled': profile.operation_tax_enabled,
            'system_tax_id': profile.operation_tax_id.id if profile.operation_tax_id else False,
            'system_price_input_mode': profile.operation_price_input_mode,
            'system_inventory_enabled': profile.use_inventory,
            'system_car_size_ids': [(6, 0, active_sizes.ids)],
            'system_size_count': len(active_sizes),
            'system_tint_count': len(selected_shades),
        }
        if film:
            price_lines = film.film_part_line_ids.price_line_ids
            priced_sizes = price_lines.mapped('car_size_id').filtered(lambda size: size)
            if price_lines:
                actual_pricing_policy = 'by_size' if priced_sizes else 'fixed'
            else:
                actual_pricing_policy = film.pricing_policy or profile.operation_pricing_policy
            use_system_pricing = (
                film.use_system_pricing_policy
                and actual_pricing_policy == profile.operation_pricing_policy
            )
            selected_sizes = film.car_size_ids or priced_sizes or active_sizes
            use_system_sizes = film.use_system_car_sizes
            if priced_sizes and set(priced_sizes.ids) != set(active_sizes.ids):
                use_system_sizes = False
            vals.update({
                'item_type': film.item_type,
                'name': film.name,
                'code': film.code,
                'description': film.description,
                'active': film.active,
                'warranty_years': film.warranty_years,
                'inventory_enabled': film.is_effected_in_inventory,
                'product_required': film.car_film_product_required,
                'warning_msg': film.warning_msg,
                'use_system_pricing_policy': use_system_pricing,
                'pricing_policy': actual_pricing_policy,
                'use_system_car_sizes': use_system_sizes,
                'car_size_ids': [(6, 0, selected_sizes.ids)],
                'use_system_commission_policy': film.use_system_commission_policy,
                'commission_event': film.commission_event or profile.commission_event,
                'commission_calculation_policy': film.commission_calculation_policy or 'fixed',
            })
        else:
            vals.update({
                'item_type': 'film',
                'active': True,
                'inventory_enabled': bool(profile.use_inventory),
                'use_system_pricing_policy': True,
                'pricing_policy': profile.operation_pricing_policy,
                'use_system_car_sizes': True,
                'car_size_ids': [(6, 0, active_sizes.ids)],
                'use_system_commission_policy': True,
                'commission_event': profile.commission_event,
                'commission_calculation_policy': 'fixed',
            })
        return self.create(vals)

    @api.onchange('use_system_pricing_policy')
    def _onchange_use_system_pricing_policy(self):
        if self.use_system_pricing_policy:
            self.pricing_policy = self.system_pricing_policy

    @api.onchange('use_system_commission_policy')
    def _onchange_use_system_commission_policy(self):
        if self.use_system_commission_policy:
            self.commission_event = self.system_commission_event

    @api.onchange('use_system_car_sizes')
    def _onchange_use_system_car_sizes(self):
        if self.use_system_car_sizes:
            self.car_size_ids = self.system_car_size_ids

    @api.onchange('item_type')
    def _onchange_item_type(self):
        # A normal service does not need film-grade-specific product selection.
        if self.item_type == 'service':
            self.product_required = False

    @api.constrains('warranty_years')
    def _check_warranty_years(self):
        for wizard in self:
            if wizard.warranty_years < 0:
                raise ValidationError(_('سنوات الضمان لا يمكن أن تكون سالبة.'))

    def _normalize_code(self, value):
        value = (value or '').strip().upper()
        value = re.sub(r'[^A-Z0-9_.-]+', '-', value).strip('-')
        return value

    def _generate_code(self):
        self.ensure_one()
        base = self._normalize_code(self.name)
        if not base:
            base = 'FS-%s' % datetime.now().strftime('%Y%m%d%H%M%S')
        candidate = base[:40]
        Film = self.env['wof.film.category'].with_context(active_test=False)
        suffix = 1
        domain = [('company_id', '=', self.company_id.id), ('code', '=', candidate)]
        if self.film_id:
            domain.append(('id', '!=', self.film_id.id))
        while Film.search_count(domain):
            suffix += 1
            candidate = '%s-%s' % (base[:34], suffix)
            domain = [('company_id', '=', self.company_id.id), ('code', '=', candidate)]
            if self.film_id:
                domain.append(('id', '!=', self.film_id.id))
        return candidate

    def _effective_values(self):
        self.ensure_one()
        pricing_policy = self.system_pricing_policy if self.use_system_pricing_policy else self.pricing_policy
        commission_event = self.system_commission_event if self.use_system_commission_policy else self.commission_event
        sizes = self.system_car_size_ids if self.use_system_car_sizes else self.car_size_ids
        if pricing_policy == 'by_size' and not sizes:
            raise ValidationError(_('حدد حجم سيارة واحدًا على الأقل عند استخدام التسعير حسب الحجم.'))
        return pricing_policy, commission_event, sizes

    def _save_basic(self):
        self.ensure_one()
        self._ensure_access()
        if not (self.name or '').strip():
            raise ValidationError(_('أدخل اسم الفيلم أو الخدمة.'))
        pricing_policy, commission_event, sizes = self._effective_values()
        code = self._normalize_code(self.code) or self._generate_code()
        vals = {
            'name': self.name.strip(),
            'code': code,
            'service_type_id': self.activity_id.id,
            'description': self.description,
            'item_type': self.item_type,
            'active': self.active,
            'warranty_years': self.warranty_years,
            'is_effected_in_inventory': self.inventory_enabled,
            'car_film_product_required': self.product_required,
            'warning_msg': self.warning_msg,
            'use_system_pricing_policy': self.use_system_pricing_policy,
            'pricing_policy': pricing_policy,
            'use_system_car_sizes': self.use_system_car_sizes,
            'car_size_ids': [(6, 0, sizes.ids)],
            'use_system_commission_policy': self.use_system_commission_policy,
            'commission_event': commission_event,
            'commission_calculation_policy': self.commission_calculation_policy,
        }
        if self.film_id:
            self.film_id.write(vals)
        else:
            self.film_id = self.env['wof.film.category'].create(vals)
            self.mode = 'edit'
        self.code = code
        return self.film_id

    def _dialog_action(self):
        self.ensure_one()
        view = self.env.ref('yousentech_wo_v4.view_wof_film_setup_wizard_form')
        return {
            'type': 'ir.actions.act_window',
            'name': _('إضافة فيلم / خدمة جديدة') if self.mode == 'create' else _('تهيئة %s') % self.name,
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(view.id, 'form')],
            'target': 'new',
            'context': dict(self.env.context),
        }

    def action_save_draft(self):
        self._save_basic()
        if self.hub_id:
            self.hub_id._refresh_films()
            return self.hub_id._reopen_hub()
        return {'type': 'ir.actions.act_window_close'}

    def action_continue(self):
        self._save_basic()
        # Stage 2 is deliberately entered through the same wizard.  The next RC
        # will replace the hand-off card with the approved tint-shades UI without
        # changing the saved Stage-1 data or its model contract.
        self.current_step = 'tint'
        return self._dialog_action()

    def action_back_basic(self):
        self.current_step = 'basic'
        return self._dialog_action()

    def action_cancel(self):
        if self.hub_id:
            self.hub_id._refresh_films()
            return self.hub_id._reopen_hub()
        return {'type': 'ir.actions.act_window_close'}
