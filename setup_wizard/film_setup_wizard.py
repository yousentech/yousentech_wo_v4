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
         ('components', 'المكونات'), ('pricing', 'التسعير'),
         ('commission', 'العمولات'), ('review', 'المراجعة والتفعيل')],
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
    system_commission_calculation_policy = fields.Selection(
        [('fixed', 'عمولة موحدة'), ('by_size', 'حسب حجم السيارة')],
        string='طريقة احتساب العمولة من النظام', readonly=True,
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

    # Tax policy: inherit company setup by default, with an explicit per-film override.
    use_system_tax_policy = fields.Boolean(string='استخدام السياسة الضريبية من النظام', default=True)
    tax_enabled = fields.Boolean(string='تطبيق الضريبة', default=True)
    tax_id = fields.Many2one(
        'account.tax', string='الضريبة', check_company=True,
        domain="[('type_tax_use', '=', 'sale'), ('company_id', '=', company_id)]",
    )
    price_input_mode = fields.Selection(
        [('excluded', 'السعر قبل الضريبة'), ('included', 'السعر شامل الضريبة')],
        string='طريقة إدخال السعر', default='excluded', required=True,
    )
    system_tax_enabled = fields.Boolean(string='تطبيق الضريبة من النظام', readonly=True)
    system_tax_id = fields.Many2one('account.tax', string='الضريبة الافتراضية من النظام', readonly=True)
    tax_price_included = fields.Boolean(
        related='tax_id.price_include', string='الضريبة شاملة السعر', readonly=True,
    )
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

    # Stage 2 — tint shades. Keep the system setup as the single source of truth
    # while allowing a film-level subset without duplicating the master degrees.
    tint_selection_mode = fields.Selection(
        [('all', 'استخدام جميع درجات النظام'), ('specific', 'اختيار درجات محددة')],
        string='طريقة استخدام درجات اللون', default='all', required=True,
    )
    system_tint_numbering_method = fields.Selection(
        [('sequential', 'ترقيم تسلسلي'), ('percentage', 'ترقيم بالنسب')],
        string='طريقة ترقيم درجات النظام', readonly=True,
    )
    tint_line_ids = fields.One2many(
        'wof.film.setup.tint.line', 'wizard_id', string='درجات اللون المتاحة',
    )
    selected_tint_count = fields.Integer(
        string='درجات اللون المختارة', compute='_compute_selected_tint_count',
    )
    tint_required = fields.Boolean(
        string='درجات اللون مطلوبة', compute='_compute_tint_required',
    )

    # Stage 3 — components. The master component defines whether it is a
    # normal car part or a service area. Service-area child parts are defined
    # once on wof.car.parts and are shown here structurally; the service area
    # itself remains the single commercial line for pricing and commission.
    component_view_mode = fields.Selection(
        [('tree', 'عرض على شكل شجرة'), ('list', 'عرض على شكل قائمة')],
        string='طريقة عرض المكونات', default='tree', required=True,
    )
    component_line_ids = fields.One2many(
        'wof.film.setup.component.line', 'wizard_id', string='المكونات',
    )
    component_top_line_ids = fields.One2many(
        'wof.film.setup.component.line', 'wizard_id', string='المكونات الرئيسية',
        domain=[('is_child', '=', False)],
    )
    selected_component_count = fields.Integer(
        string='المكونات المختارة', compute='_compute_component_summary',
    )
    service_area_count = fields.Integer(
        string='مناطق الخدمة', compute='_compute_component_summary',
    )
    structural_part_count = fields.Integer(
        string='الأجزاء البنيوية', compute='_compute_component_summary',
    )


    # Stage 4 — commercial pricing and commissions.  The persistent film-part
    # line remains the commercial unit; service-area children never receive
    # independent price/commission rows.
    pricing_tab = fields.Selection(
        [('price', 'التسعير'), ('commission', 'العمولات')],
        string='تبويب الأسعار والعمولات', default='price', required=True,
    )
    commercial_line_ids = fields.One2many(
        'wof.film.setup.commercial.line', 'wizard_id', string='المكونات التجارية',
    )
    price_complete_count = fields.Integer(compute='_compute_commercial_summary')
    price_missing_count = fields.Integer(compute='_compute_commercial_summary')
    commission_complete_count = fields.Integer(compute='_compute_commercial_summary')
    commission_missing_count = fields.Integer(compute='_compute_commercial_summary')

    @api.depends(
        'commercial_line_ids.price_complete',
        'commercial_line_ids.commission_complete',
    )
    def _compute_commercial_summary(self):
        for wizard in self:
            lines = wizard.commercial_line_ids
            price_lines = lines.filtered(lambda rec: not rec.commission_basis_only)
            wizard.price_complete_count = len(price_lines.filtered('price_complete'))
            wizard.price_missing_count = len(price_lines.filtered(lambda rec: not rec.price_complete))
            wizard.commission_complete_count = len(lines.filtered('commission_complete'))
            wizard.commission_missing_count = len(lines.filtered(lambda rec: not rec.commission_complete))

    @api.depends('component_line_ids.selected', 'component_line_ids.part_type',
                 'component_line_ids.is_child')
    def _compute_component_summary(self):
        for wizard in self:
            top = wizard.component_line_ids.filtered(lambda line: not line.is_child and line.selected)
            wizard.selected_component_count = len(top)
            wizard.service_area_count = len(top.filtered(lambda line: line.part_type == 'service_area'))
            wizard.structural_part_count = len(wizard.component_line_ids.filtered(
                lambda line: line.is_child and line.parent_selected
            ))

    @api.depends('supports_color_grades', 'item_type')
    def _compute_tint_required(self):
        for wizard in self:
            wizard.tint_required = bool(wizard.supports_color_grades and wizard.item_type == 'film')

    @api.depends('tint_selection_mode', 'tint_line_ids.selected')
    def _compute_selected_tint_count(self):
        for wizard in self:
            wizard.selected_tint_count = len(wizard.tint_line_ids.filtered('selected'))

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
            'system_commission_calculation_policy': 'by_size' if profile.advanced_commission else 'fixed',
            'system_tax_enabled': profile.operation_tax_enabled,
            'system_tax_id': profile.operation_tax_id.id if profile.operation_tax_id else False,
            'system_price_input_mode': profile.operation_price_input_mode,
            'system_inventory_enabled': profile.use_inventory,
            'system_car_size_ids': [(6, 0, active_sizes.ids)],
            'system_size_count': len(active_sizes),
            'system_tint_count': len(selected_shades),
            'system_tint_numbering_method': profile.tint_numbering_method,
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
                'commission_calculation_policy': (
                    ('by_size' if profile.advanced_commission else 'fixed')
                    if film.use_system_commission_policy
                    else (film.commission_calculation_policy or 'fixed')
                ),
                'use_system_tax_policy': film.use_system_tax_policy,
                'tax_enabled': film.tax_enabled if not film.use_system_tax_policy else profile.operation_tax_enabled,
                'tax_id': (film.tax_id.id if film.tax_id else False) if not film.use_system_tax_policy else (profile.operation_tax_id.id if profile.operation_tax_id else False),
                'price_input_mode': film.price_input_mode if not film.use_system_tax_policy else profile.operation_price_input_mode,
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
                'commission_calculation_policy': 'by_size' if profile.advanced_commission else 'fixed',
                'use_system_tax_policy': True,
                'tax_enabled': profile.operation_tax_enabled,
                'tax_id': profile.operation_tax_id.id if profile.operation_tax_id else False,
                'price_input_mode': profile.operation_price_input_mode,
            })
        # Infer the Stage-2 mode from existing data for backward-compatible upgrades.
        if film and activity.supports_color_grades and film.item_type == 'film':
            system_codes = set(selected_shades.mapped('code'))
            active_grade_codes = set(film.film_category_line_ids.filtered('active').mapped('code'))
            use_all = bool(system_codes) and active_grade_codes == system_codes
            if hasattr(film, 'use_system_tint_grades'):
                use_all = bool(film.use_system_tint_grades) or use_all
            vals['tint_selection_mode'] = 'all' if use_all else 'specific'
        else:
            vals['tint_selection_mode'] = 'all'

        wizard = self.create(vals)
        wizard._prepare_tint_lines(selected_shades=selected_shades)
        return wizard

    def _prepare_tint_lines(self, selected_shades=None):
        self.ensure_one()
        self.tint_line_ids.unlink()
        selected_shades = selected_shades or self.profile_id.tint_shade_line_ids.filtered('selected')
        existing_codes = set()
        existing_values = set()
        if self.film_id:
            existing = self.film_id.film_category_line_ids.filtered('active')
            existing_codes = set(existing.mapped('code'))
            existing_values = set(existing.mapped('name'))
        vals_list = []
        for line in selected_shades.sorted(lambda rec: (rec.sequence, rec.id)):
            selected = True
            if self.tint_selection_mode == 'specific' and self.film_id:
                selected = line.code in existing_codes or line.value in existing_values
            vals_list.append({
                'wizard_id': self.id,
                'sequence': line.sequence,
                'value': line.value,
                'code': line.code,
                'selected': selected,
            })
        if vals_list:
            self.env['wof.film.setup.tint.line'].create(vals_list)

    @api.onchange('use_system_pricing_policy')
    def _onchange_use_system_pricing_policy(self):
        if self.use_system_pricing_policy:
            self.pricing_policy = self.system_pricing_policy

    @api.onchange('use_system_tax_policy')
    def _onchange_use_system_tax_policy(self):
        if self.use_system_tax_policy:
            self.tax_enabled = self.system_tax_enabled
            self.tax_id = self.system_tax_id
            self.price_input_mode = (
                'included'
                if self.system_tax_id and self.system_tax_id.price_include
                else self.system_price_input_mode
            )

    @api.onchange('tax_id')
    def _onchange_tax_id_price_include(self):
        """A price-included tax defines the input mode; do not allow a contradictory mode."""
        if not self.use_system_tax_policy and self.tax_id and self.tax_id.price_include:
            self.price_input_mode = 'included'

    @api.onchange('use_system_commission_policy')
    def _onchange_use_system_commission_policy(self):
        if self.use_system_commission_policy:
            self.commission_event = self.system_commission_event
            self.commission_calculation_policy = self.system_commission_calculation_policy

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
        commission_calculation_policy = (
            self.system_commission_calculation_policy
            if self.use_system_commission_policy
            else self.commission_calculation_policy
        )
        sizes = self.system_car_size_ids if self.use_system_car_sizes else self.car_size_ids
        tax_enabled = self.system_tax_enabled if self.use_system_tax_policy else self.tax_enabled
        tax_id = self.system_tax_id if self.use_system_tax_policy else self.tax_id
        price_input_mode = self.system_price_input_mode if self.use_system_tax_policy else self.price_input_mode
        if tax_enabled and tax_id and tax_id.price_include:
            price_input_mode = 'included'
        if pricing_policy == 'by_size' and not sizes:
            raise ValidationError(_('حدد حجم سيارة واحدًا على الأقل عند استخدام التسعير حسب الحجم.'))
        if tax_enabled and not tax_id:
            raise ValidationError(_('حدد الضريبة المستخدمة، أو أوقف تطبيق الضريبة لهذا الفيلم / الخدمة.'))
        return (
            pricing_policy, commission_event, commission_calculation_policy,
            sizes, tax_enabled, tax_id, price_input_mode,
        )

    def _save_basic(self):
        self.ensure_one()
        self._ensure_access()
        if not (self.name or '').strip():
            raise ValidationError(_('أدخل اسم الفيلم أو الخدمة.'))
        (
            pricing_policy, commission_event, commission_calculation_policy,
            sizes, tax_enabled, tax_id, price_input_mode,
        ) = self._effective_values()
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
            'commission_calculation_policy': commission_calculation_policy,
            'use_system_tax_policy': self.use_system_tax_policy,
            'tax_enabled': tax_enabled,
            'tax_id': tax_id.id if tax_id else False,
            'price_input_mode': price_input_mode,
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
        self.current_step = 'tint'
        return self._dialog_action()

    def action_back_basic(self):
        self.current_step = 'basic'
        return self._dialog_action()

    def action_use_all_tints(self):
        self.ensure_one()
        self.tint_selection_mode = 'all'
        self.tint_line_ids.write({'selected': True})
        return self._dialog_action()

    def action_use_specific_tints(self):
        self.ensure_one()
        self.tint_selection_mode = 'specific'
        # Preserve the current set; when switching from 'all' the user starts
        # from all enabled and can remove only the shades that do not apply.
        return self._dialog_action()

    def _save_tint(self):
        self.ensure_one()
        self._ensure_access()
        if not self.film_id:
            self._save_basic()
        Grade = self.env['wof.film.category.lines'].with_context(active_test=False)
        existing = Grade.search([('header_id', '=', self.film_id.id)])

        if not self.tint_required:
            if existing:
                existing.write({'active': False})
            if hasattr(self.film_id, 'use_system_tint_grades'):
                self.film_id.use_system_tint_grades = True
            return True

        lines = self.tint_line_ids.filtered('selected')
        if self.tint_selection_mode == 'all':
            lines = self.tint_line_ids
            if lines.filtered(lambda rec: not rec.selected):
                lines.write({'selected': True})
        if not lines:
            raise ValidationError(_('اختر درجة لون واحدة على الأقل لهذا الفيلم.'))

        selected_codes = set(lines.mapped('code'))
        selected_values = set(lines.mapped('value'))
        for line in lines:
            grade = existing.filtered(lambda rec: rec.code == line.code)[:1]
            if not grade:
                grade = existing.filtered(lambda rec: rec.name == line.value)[:1]
            vals = {
                'header_id': self.film_id.id,
                'sequence': line.sequence,
                'name': line.value,
                'code': line.code,
                'active': True,
            }
            # Percentage-numbered degrees also carry a useful transmission value.
            if self.system_tint_numbering_method == 'percentage':
                digits = re.sub(r'[^0-9]', '', line.value or '')
                if digits:
                    vals['transmission_percent'] = max(0, min(100, int(digits)))
            if grade:
                grade.write(vals)
            else:
                Grade.create(vals)

        # Archive, rather than delete, degrees removed from this film so old
        # installation orders that reference them remain historically valid.
        for grade in existing.filtered('active'):
            if grade.code:
                keep = grade.code in selected_codes
            else:
                keep = grade.name in selected_values
            if not keep:
                grade.write({'active': False})

        if hasattr(self.film_id, 'use_system_tint_grades'):
            self.film_id.use_system_tint_grades = self.tint_selection_mode == 'all'
        return True

    def action_continue_tint(self):
        self._save_tint()
        self.current_step = 'components'
        self._prepare_component_lines()
        return self._dialog_action()

    def _prepare_component_lines(self):
        self.ensure_one()
        self.component_line_ids.unlink()
        if not self.film_id:
            return
        existing_part_ids = set(self.film_id.film_part_line_ids.filtered('part_selected').mapped('car_part_id').ids)
        masters = self.env['wof.car.parts'].with_context(active_test=False).search([
            ('company_id', '=', self.company_id.id),
            ('active', '=', True),
        ], order='priority_part, name, id')
        vals = []
        seq = 10
        for part in masters:
            # Top-level component row. Existing film selections remain selected;
            # new masters remain available in the add dialog instead of cluttering the tree.
            if part.id not in existing_part_ids:
                continue
            vals.append({
                'wizard_id': self.id,
                'sequence': seq,
                'car_part_id': part.id,
                'selected': True,
                'is_child': False,
            })
            parent_seq = seq
            seq += 10
            if part.part_type == 'service_area':
                for child in part.service_area_part_ids.sorted(lambda rec: (rec.priority_part, rec.name or '', rec.id)):
                    vals.append({
                        'wizard_id': self.id,
                        'sequence': parent_seq + 1,
                        'car_part_id': child.id,
                        'selected': True,
                        'is_child': True,
                        'parent_master_id': part.id,
                    })
                    parent_seq += 1
        if vals:
            self.env['wof.film.setup.component.line'].create(vals)

    def _append_component_master(self, part):
        self.ensure_one()
        part.ensure_one()
        if part.company_id != self.company_id or not part.active:
            raise ValidationError(_('المكوّن المحدد غير متاح لهذه الشركة.'))
        existing = self.component_line_ids.filtered(
            lambda line: not line.is_child and line.car_part_id == part
        )[:1]
        if existing:
            existing.selected = True
            return existing
        max_seq = max(self.component_line_ids.mapped('sequence') or [0])
        parent = self.env['wof.film.setup.component.line'].create({
            'wizard_id': self.id, 'sequence': max_seq + 10,
            'car_part_id': part.id, 'selected': True, 'is_child': False,
        })
        if part.part_type == 'service_area':
            child_seq = parent.sequence + 1
            for child in part.service_area_part_ids.sorted(lambda rec: (rec.priority_part, rec.name or '', rec.id)):
                self.env['wof.film.setup.component.line'].create({
                    'wizard_id': self.id, 'sequence': child_seq,
                    'car_part_id': child.id, 'selected': True, 'is_child': True,
                    'parent_master_id': part.id,
                })
                child_seq += 1
        return parent

    def action_add_component(self):
        self.ensure_one()
        dialog = self.env['wof.film.setup.component.dialog'].create({
            'wizard_id': self.id, 'expected_type': 'car_part',
        })
        return dialog._dialog_action()

    def action_add_service_area(self):
        self.ensure_one()
        dialog = self.env['wof.film.setup.component.dialog'].create({
            'wizard_id': self.id, 'expected_type': 'service_area',
        })
        return dialog._dialog_action()

    def action_component_tree_view(self):
        self.component_view_mode = 'tree'
        return self._dialog_action()

    def action_component_list_view(self):
        self.component_view_mode = 'list'
        return self._dialog_action()

    def _save_components(self):
        self.ensure_one()
        self._ensure_access()
        if not self.film_id:
            self._save_basic()
        selected = self.component_line_ids.filtered(lambda line: not line.is_child and line.selected)
        if not selected:
            raise ValidationError(_('أضف مكوّنًا واحدًا على الأقل للفيلم / الخدمة.'))
        empty_areas = selected.filtered(
            lambda line: line.part_type == 'service_area' and not line.car_part_id.service_area_part_ids
        )
        if empty_areas:
            raise ValidationError(_('منطقة الخدمة يجب أن تحتوي على جزء واحد على الأقل في تعريف المكوّن قبل استخدامها.'))
        Line = self.env['wof.film.parts.lines']
        existing = Line.search([('header_id', '=', self.film_id.id)])
        selected_ids = set(selected.mapped('car_part_id').ids)
        # Preserve historical price/commission records by deactivating the film
        # selection flag instead of deleting existing component lines.
        for old_line in existing:
            old_line.part_selected = old_line.car_part_id.id in selected_ids
        seq = 10
        for line in selected.sorted(lambda rec: (rec.sequence, rec.id)):
            target = existing.filtered(lambda rec: rec.car_part_id == line.car_part_id)[:1]
            vals = {'header_id': self.film_id.id, 'car_part_id': line.car_part_id.id,
                    'part_selected': True, 'sequence': seq}
            if target:
                target.write(vals)
            else:
                Line.create(vals)
            seq += 10
        return True

    def _prepare_commercial_lines(self):
        self.ensure_one()
        self.commercial_line_ids.unlink()
        if not self.film_id:
            return
        vals = []
        for part_line in self.film_id.film_part_line_ids.filtered('part_selected').sorted(
            lambda rec: (rec.sequence, rec.id)
        ):
            vals.append({
                'wizard_id': self.id,
                'sequence': part_line.sequence,
                'part_line_id': part_line.id,
            })
        if vals:
            self.env['wof.film.setup.commercial.line'].create(vals)

    def action_continue_components(self):
        self._save_components()
        self.current_step = 'pricing'
        self.pricing_tab = 'price'
        self._prepare_commercial_lines()
        return self._dialog_action()

    def action_pricing_tab_price(self):
        self.ensure_one()
        self.current_step = 'pricing'
        self.pricing_tab = 'price'
        return self._dialog_action()

    def action_pricing_tab_commission(self):
        self.ensure_one()
        self.current_step = 'commission'
        self.pricing_tab = 'commission'
        return self._dialog_action()

    def action_continue_pricing(self):
        """Stage 4 validates pricing only, then hands off to commissions."""
        self.ensure_one()
        if not self.commercial_line_ids:
            self._prepare_commercial_lines()
        missing_prices = self.commercial_line_ids.filtered(lambda rec: not rec.price_complete)
        if missing_prices:
            raise ValidationError(_(
                'أكمل تسعير جميع المكونات أو حددها كمجانية قبل المتابعة. المكونات الناقصة: %s'
            ) % '، '.join(missing_prices.mapped('part_name')))
        self.current_step = 'commission'
        self.pricing_tab = 'commission'
        # Rebuild the transient commercial list, then expose structural child
        # rows only when a service area is configured to derive commission.
        self._prepare_commercial_lines()
        for area in self.commercial_line_ids.filtered(lambda rec: rec.part_type == 'service_area' and rec.part_line_id.service_commission_source == 'from_parts'):
            area._ensure_commission_basis_lines()
        return self._dialog_action()

    def action_continue_commission(self):
        """Stage 5 validates commissions and materializes derived service-area totals."""
        self.ensure_one()
        if not self.commercial_line_ids:
            self._prepare_commercial_lines()
        # Derived service-area commission rows are snapshots used by the current
        # runtime pricing resolver. Their source remains the child components.
        for line in self.commercial_line_ids.filtered(lambda rec: rec.part_type == 'service_area'):
            if line.part_line_id.service_commission_source == 'from_parts':
                line._sync_commission_from_children()
        missing_commissions = self.commercial_line_ids.filtered(lambda rec: not rec.commission_complete)
        if missing_commissions:
            raise ValidationError(_(
                'أكمل إعداد عمولة جميع المكونات قبل المتابعة. المكونات الناقصة: %s'
            ) % '، '.join(missing_commissions.mapped('part_name')))
        self.current_step = 'review'
        return self._dialog_action()

    def action_back_pricing(self):
        self.ensure_one()
        self.current_step = 'pricing'
        self.pricing_tab = 'price'
        self._prepare_commercial_lines()
        return self._dialog_action()

    def action_back_components(self):
        self.current_step = 'components'
        if not self.component_line_ids and self.film_id:
            self._prepare_component_lines()
        return self._dialog_action()

    def action_back_tint(self):
        self.current_step = 'tint'
        return self._dialog_action()

    def action_cancel(self):
        if self.hub_id:
            self.hub_id._refresh_films()
            return self.hub_id._reopen_hub()
        return {'type': 'ir.actions.act_window_close'}


class WofFilmSetupComponentLine(models.TransientModel):
    _name = 'wof.film.setup.component.line'
    _description = 'مكوّن في معالج تهيئة الفيلم'
    _order = 'sequence, id'

    wizard_id = fields.Many2one('wof.film.setup.wizard', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    car_part_id = fields.Many2one('wof.car.parts', string='المكوّن', required=True, ondelete='cascade')
    # Dedicated plain-text label for the custom Kanban.  Odoo's many2one
    # record.value can collapse/come back empty in this compact embedded Kanban,
    # while the related master name is deterministic and keeps RTL rendering stable.
    part_name = fields.Char(related='car_part_id.name', string='اسم المكوّن', readonly=True, store=True)
    part_type = fields.Selection(related='car_part_id.part_type', string='النوع', readonly=True)
    code = fields.Char(related='car_part_id.code', readonly=True)
    selected = fields.Boolean(default=True)
    is_child = fields.Boolean(string='جزء داخلي', default=False, readonly=True)
    parent_master_id = fields.Many2one('wof.car.parts', string='منطقة الخدمة', readonly=True)
    parent_selected = fields.Boolean(compute='_compute_parent_selected')
    expanded = fields.Boolean(string='إظهار أجزاء منطقة الخدمة', default=False)
    parent_expanded = fields.Boolean(compute='_compute_parent_expanded')
    child_count = fields.Integer(compute='_compute_child_count')
    child_names = fields.Char(compute='_compute_child_count')

    @api.depends('wizard_id.component_line_ids.selected', 'parent_master_id')
    def _compute_parent_selected(self):
        for line in self:
            if not line.is_child or not line.parent_master_id:
                line.parent_selected = False
                continue
            parent = line.wizard_id.component_line_ids.filtered(
                lambda rec: not rec.is_child and rec.car_part_id == line.parent_master_id
            )[:1]
            line.parent_selected = bool(parent and parent.selected)

    @api.depends('wizard_id.component_line_ids.expanded', 'parent_master_id')
    def _compute_parent_expanded(self):
        for line in self:
            if not line.is_child or not line.parent_master_id:
                line.parent_expanded = False
                continue
            parent = line.wizard_id.component_line_ids.filtered(
                lambda rec: not rec.is_child and rec.car_part_id == line.parent_master_id
            )[:1]
            line.parent_expanded = bool(parent and parent.expanded)

    @api.depends('car_part_id.service_area_part_ids')
    def _compute_child_count(self):
        for line in self:
            children = line.car_part_id.service_area_part_ids if line.part_type == 'service_area' else self.env['wof.car.parts']
            line.child_count = len(children)
            line.child_names = '، '.join(children.mapped('name'))

    def action_toggle_children(self):
        """Open/collapse the structural children of a service-area row.

        This method belongs to the component-line model because the kanban
        object button is rendered on ``wof.film.setup.component.line``.
        Keeping the state on the transient parent row also means the toggle is
        purely visual and never changes the persistent component definition.
        """
        self.ensure_one()
        if self.is_child or self.part_type != 'service_area':
            return self.wizard_id._dialog_action()
        self.expanded = not self.expanded
        return self.wizard_id._dialog_action()

    def action_edit(self):
        self.ensure_one()
        if self.is_child:
            return self.wizard_id._dialog_action()
        dialog = self.env['wof.film.setup.component.dialog'].create({
            'wizard_id': self.wizard_id.id,
            'expected_type': self.part_type,
            'line_id': self.id,
            'car_part_id': self.car_part_id.id,
        })
        return dialog._dialog_action()

    def action_remove(self):
        self.ensure_one()
        wizard = self.wizard_id
        if self.is_child:
            return wizard._dialog_action()
        # Remove transient row and all visual children. Persistent data is only
        # changed when the user continues to the next step.
        wizard.component_line_ids.filtered(
            lambda rec: rec.is_child and rec.parent_master_id == self.car_part_id
        ).unlink()
        self.unlink()
        return wizard._dialog_action()

    def action_move_up(self):
        self.ensure_one()
        if self.is_child:
            return self.wizard_id._dialog_action()
        siblings = self.wizard_id.component_line_ids.filtered(lambda rec: not rec.is_child).sorted(lambda rec: (rec.sequence, rec.id))
        idx = list(siblings).index(self)
        if idx > 0:
            prev = siblings[idx - 1]
            old_seq = self.sequence
            self.sequence = prev.sequence
            prev.sequence = old_seq
        return self.wizard_id._dialog_action()


class WofFilmSetupComponentDialog(models.TransientModel):
    _name = 'wof.film.setup.component.dialog'
    _description = 'اختيار مكوّن للفيلم'

    wizard_id = fields.Many2one('wof.film.setup.wizard', required=True, ondelete='cascade', readonly=True)
    company_id = fields.Many2one(related='wizard_id.company_id', readonly=True)
    expected_type = fields.Selection([('car_part', 'جزء سيارة'), ('service_area', 'منطقة خدمة')], required=True, readonly=True)
    line_id = fields.Many2one('wof.film.setup.component.line', string='السطر الحالي', readonly=True)
    # Do not make this field ORM-required: the transient dialog itself must be
    # created first so Odoo can open the popup, then the user chooses a component.
    # Business-required validation is enforced in action_confirm().
    car_part_id = fields.Many2one(
        'wof.car.parts', string='المكوّن', required=False,
        domain="[('company_id', '=', company_id), ('active', '=', True), ('part_type', '=', expected_type)]",
    )
    child_part_ids = fields.Many2many(related='car_part_id.service_area_part_ids', readonly=True)

    def _dialog_action(self):
        self.ensure_one()
        view = self.env.ref('yousentech_wo_v4.view_wof_film_setup_component_dialog_form')
        return {
            'type': 'ir.actions.act_window', 'name': _('إضافة مكوّن') if self.expected_type == 'car_part' else _('إضافة منطقة خدمة'),
            'res_model': self._name, 'res_id': self.id, 'view_mode': 'form',
            'views': [(view.id, 'form')], 'target': 'new', 'context': dict(self.env.context),
        }

    def action_create_new(self):
        self.ensure_one()
        create_dialog = self.env['wof.film.setup.component.create.dialog'].create({
            'wizard_id': self.wizard_id.id,
            'source_dialog_id': self.id,
            'expected_type': self.expected_type,
        })
        return create_dialog._dialog_action()

    def action_confirm(self):
        self.ensure_one()
        if not self.car_part_id:
            raise ValidationError(_('اختر المكوّن أولاً قبل الإضافة.'))
        if self.car_part_id.part_type != self.expected_type:
            raise ValidationError(_('نوع المكوّن المحدد لا يطابق نوع الإضافة.'))
        if self.expected_type == 'service_area' and not self.car_part_id.service_area_part_ids:
            raise ValidationError(_('منطقة الخدمة المحددة لا تحتوي على أجزاء. أضف أجزاءها من تعريف المكوّن أولاً.'))
        duplicate = self.wizard_id.component_line_ids.filtered(
            lambda line: not line.is_child and line.car_part_id == self.car_part_id
            and (not self.line_id or line != self.line_id)
        )
        if duplicate:
            raise ValidationError(_('هذا المكوّن مضاف بالفعل لهذا الفيلم / الخدمة.'))
        if self.line_id:
            old_part = self.line_id.car_part_id
            self.wizard_id.component_line_ids.filtered(
                lambda rec: rec.is_child and rec.parent_master_id == old_part
            ).unlink()
            self.line_id.car_part_id = self.car_part_id
            if self.car_part_id.part_type == 'service_area':
                seq = self.line_id.sequence + 1
                for child in self.car_part_id.service_area_part_ids.sorted(
                    lambda rec: (rec.priority_part, rec.name or '', rec.id)
                ):
                    self.env['wof.film.setup.component.line'].create({
                        'wizard_id': self.wizard_id.id, 'sequence': seq,
                        'car_part_id': child.id, 'selected': True, 'is_child': True,
                        'parent_master_id': self.car_part_id.id,
                    })
                    seq += 1
        else:
            self.wizard_id._append_component_master(self.car_part_id)
        return self.wizard_id._dialog_action()


class WofFilmSetupComponentCreateDialog(models.TransientModel):
    _name = 'wof.film.setup.component.create.dialog'
    _description = 'إنشاء مكوّن جديد من معالج الفيلم'

    wizard_id = fields.Many2one(
        'wof.film.setup.wizard', required=True, ondelete='cascade', readonly=True,
    )
    source_dialog_id = fields.Many2one(
        'wof.film.setup.component.dialog', string='نافذة الاختيار',
        ondelete='set null', readonly=True,
    )
    company_id = fields.Many2one(related='wizard_id.company_id', readonly=True)
    expected_type = fields.Selection(
        [('car_part', 'جزء سيارة'), ('service_area', 'منطقة خدمة')],
        required=True, readonly=True,
    )
    name = fields.Char(string='اسم المكوّن')
    code = fields.Char(
        string='الكود',
        help='اختياري. إذا تركته فارغًا سيتم إنشاء كود تلقائي فريد داخل الشركة.',
    )
    auto_create_product = fields.Boolean(
        string='إنشاء صنف خدمي تلقائيًا', default=True,
        help='ينشئ صنف خدمة مرتبطًا بالمكوّن بنفس الاسم. ألغِ الخيار إذا أردت ربط صنف خدمي موجود.',
    )
    product_id = fields.Many2one(
        'product.product', string='الصنف الخدمي',
        domain="[('type', '=', 'service')]",
    )
    priority_part = fields.Integer(string='ترتيب الأولوية', default=10)
    service_area_part_ids = fields.Many2many(
        'wof.car.parts',
        'wof_film_component_create_area_part_rel',
        'dialog_id', 'part_id',
        string='أجزاء منطقة الخدمة',
        domain="[('company_id', '=', company_id), ('part_type', '=', 'car_part'), ('active', '=', True)]",
    )
    part_options_required = fields.Boolean(string='الخيارات الإضافية إجبارية')
    part_options_ids = fields.Many2many(
        'wof.car.part.options',
        'wof_film_component_create_option_rel',
        'dialog_id', 'option_id',
        string='خيارات إضافية',
        domain="[('active', '=', True)]",
    )
    notes = fields.Char(string='ملاحظات')
    warning_msg = fields.Char(string='رسالة تحذير')

    def _dialog_action(self):
        self.ensure_one()
        view = self.env.ref('yousentech_wo_v4.view_wof_film_setup_component_create_dialog_form')
        title = _('إنشاء جزء سيارة جديد') if self.expected_type == 'car_part' else _('إنشاء منطقة خدمة جديدة')
        return {
            'type': 'ir.actions.act_window',
            'name': title,
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(view.id, 'form')],
            'target': 'new',
            'context': dict(self.env.context),
        }

    def action_back_to_selection(self):
        self.ensure_one()
        if self.source_dialog_id:
            return self.source_dialog_id._dialog_action()
        return {'type': 'ir.actions.act_window_close'}

    def _generate_component_code(self):
        self.ensure_one()
        prefix = 'AREA' if self.expected_type == 'service_area' else 'PART'
        Master = self.env['wof.car.parts'].with_context(active_test=False)
        # Keep generated codes readable while guaranteeing uniqueness per company.
        number = Master.search_count([
            ('company_id', '=', self.company_id.id),
            ('part_type', '=', self.expected_type),
        ]) + 1
        for _attempt in range(10000):
            code = '%s-%04d' % (prefix, number)
            if not Master.search_count([
                ('company_id', '=', self.company_id.id), ('code', '=', code),
            ]):
                return code
            number += 1
        raise ValidationError(_('تعذر إنشاء كود تلقائي فريد للمكوّن. أدخل الكود يدويًا.'))

    def _resolve_service_product(self):
        self.ensure_one()
        if not self.auto_create_product:
            if not self.product_id:
                raise ValidationError(_('اختر الصنف الخدمي المرتبط بالمكوّن.'))
            if self.product_id.type != 'service':
                raise ValidationError(_('الصنف المرتبط بالمكوّن يجب أن يكون من نوع خدمة.'))
            return self.product_id

        Product = self.env['product.product']
        vals = {
            'name': (self.name or '').strip(),
            'type': 'service',
            'sale_ok': True,
            'purchase_ok': False,
        }
        return Product.create(vals)

    def action_create_and_add(self):
        self.ensure_one()
        self.wizard_id._ensure_access()
        name = (self.name or '').strip()
        if not name:
            raise ValidationError(_('أدخل اسم المكوّن أولاً.'))
        if self.expected_type == 'service_area' and not self.service_area_part_ids:
            raise ValidationError(_('حدد جزءًا واحدًا على الأقل داخل منطقة الخدمة.'))

        Master = self.env['wof.car.parts'].with_context(active_test=False)
        duplicate_name = Master.search([
            ('company_id', '=', self.company_id.id),
            ('name', '=ilike', name),
        ], limit=1)
        if duplicate_name:
            raise ValidationError(_(
                'يوجد مكوّن باسم "%s" بالفعل. ارجع إلى نافذة الاختيار واختره بدل إنشاء نسخة مكررة.'
            ) % duplicate_name.display_name)

        code = (self.code or '').strip() or self._generate_component_code()
        if Master.search_count([
            ('company_id', '=', self.company_id.id), ('code', '=', code),
        ]):
            raise ValidationError(_('كود المكوّن "%s" مستخدم مسبقًا في هذه الشركة.') % code)

        product = self._resolve_service_product()
        vals = {
            'name': name,
            'code': code,
            'part_type': self.expected_type,
            'company_id': self.company_id.id,
            'product_id': product.id,
            'priority_part': self.priority_part,
            'part_options_required': self.part_options_required,
            'part_options_ids': [(6, 0, self.part_options_ids.ids)],
            'notes': self.notes,
            'warning_msg': self.warning_msg,
            'active': True,
        }
        if self.expected_type == 'service_area':
            vals['service_area_part_ids'] = [(6, 0, self.service_area_part_ids.ids)]

        part = Master.create(vals)
        # The user created the master from this film flow, so add it immediately
        # to the current film and let the existing tree builder create area children.
        self.wizard_id._append_component_master(part)
        return self.wizard_id._dialog_action()



class WofFilmSetupCommercialLine(models.TransientModel):
    _name = 'wof.film.setup.commercial.line'
    _description = 'سطر تسعير وعمولة في معالج الفيلم'
    _order = 'sequence, id'

    wizard_id = fields.Many2one('wof.film.setup.wizard', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    part_line_id = fields.Many2one('wof.film.parts.lines', required=True, ondelete='cascade', readonly=True)
    car_part_id = fields.Many2one(related='part_line_id.car_part_id', readonly=True)
    part_name = fields.Char(related='part_line_id.car_part_id.name', readonly=True)
    part_type = fields.Selection(related='part_line_id.car_part_id.part_type', readonly=True)
    pricing_tab = fields.Selection(related='wizard_id.pricing_tab', readonly=True)
    child_names = fields.Char(compute='_compute_child_names')
    price_expanded = fields.Boolean(default=False)
    commission_expanded = fields.Boolean(default=False)
    price_complete = fields.Boolean(compute='_compute_completion')
    price_missing_count = fields.Integer(compute='_compute_completion')
    commission_complete = fields.Boolean(compute='_compute_completion')
    commission_missing_count = fields.Integer(compute='_compute_completion')
    price_summary = fields.Char(compute='_compute_completion')
    commission_summary = fields.Char(compute='_compute_completion')
    price_is_free = fields.Boolean(compute='_compute_completion')
    service_commission_source = fields.Selection(related='part_line_id.service_commission_source', readonly=True)
    technician_commission_distribution = fields.Selection(related='part_line_id.technician_commission_distribution', readonly=True)
    derived_commission_details = fields.Char(compute='_compute_completion')
    commission_basis_only = fields.Boolean(string='أساس عمولة فقط', default=False, readonly=True)
    parent_service_area_id = fields.Many2one('wof.car.parts', string='منطقة الخدمة الأم', readonly=True)

    @api.depends('car_part_id.service_area_part_ids')
    def _compute_child_names(self):
        for rec in self:
            rec.child_names = '، '.join(rec.car_part_id.service_area_part_ids.mapped('name')) if rec.part_type == 'service_area' else ''

    def _ensure_commission_basis_lines(self):
        self.ensure_one()
        if self.part_type != 'service_area':
            return self.env['wof.film.setup.commercial.line']
        FilmPart = self.env['wof.film.parts.lines']
        Commercial = self.env['wof.film.setup.commercial.line']
        created = Commercial
        for idx, child in enumerate(self.car_part_id.service_area_part_ids, start=1):
            part_line = self.wizard_id.film_id.film_part_line_ids.filtered(lambda line: line.car_part_id == child)[:1]
            if not part_line:
                part_line = FilmPart.create({
                    'header_id': self.wizard_id.film_id.id,
                    'car_part_id': child.id,
                    'part_selected': False,
                    'sequence': self.sequence + idx,
                })
            existing = self.wizard_id.commercial_line_ids.filtered(lambda line: line.part_line_id == part_line)[:1]
            if not existing:
                existing = Commercial.create({
                    'wizard_id': self.wizard_id.id,
                    'sequence': self.sequence + idx,
                    'part_line_id': part_line.id,
                    'commission_basis_only': True,
                    'parent_service_area_id': self.car_part_id.id,
                })
                created |= existing
        return created

    def _child_part_lines(self):
        self.ensure_one()
        if self.part_type != 'service_area':
            return self.env['wof.film.parts.lines']
        child_ids = self.car_part_id.service_area_part_ids.ids
        return self.wizard_id.film_id.film_part_line_ids.filtered(lambda line: line.car_part_id.id in child_ids)

    def _commission_value_for_size(self, part_line, size=False):
        lines = part_line.commission_line_ids
        found = self.env['wof.film.parts.commission.lines']
        if size:
            found = lines.filtered(lambda line: line.car_size_id == size)[:1]
        if not found:
            found = lines.filtered(lambda line: not line.car_size_id)[:1]
        if not found:
            return 0.0, False
        value = found.commission or 0.0
        if part_line.commission_value_type == 'percent':
            prices = part_line.price_line_ids
            price = prices.filtered(lambda line: line.car_size_id == size)[:1] if size else self.env['wof.film.parts.price.lines']
            if not price:
                price = prices.filtered(lambda line: not line.car_size_id)[:1]
            value = (price.part_price if price else 0.0) * value / 100.0
        return value, True

    def _derived_commission_values(self):
        self.ensure_one()
        children = self.car_part_id.service_area_part_ids
        child_lines = self._child_part_lines()
        line_by_part = {line.car_part_id.id: line for line in child_lines}
        missing_parts = children.filtered(lambda part: part.id not in line_by_part)
        if missing_parts:
            return [], missing_parts.mapped('name')
        values = []
        missing = []
        if self.wizard_id.commission_calculation_policy == 'by_size':
            for size in self.wizard_id.film_id.car_size_ids:
                total = 0.0
                ok = True
                for part in children:
                    value, found = self._commission_value_for_size(line_by_part[part.id], size)
                    total += value
                    ok = ok and found
                if not ok:
                    missing.append(size.name)
                values.append((size, total))
        else:
            total = 0.0
            for part in children:
                value, found = self._commission_value_for_size(line_by_part[part.id], False)
                total += value
                if not found:
                    missing.append(part.name)
            values.append((False, total))
        return values, missing

    def _sync_commission_from_children(self):
        self.ensure_one()
        if self.part_type != 'service_area' or self.part_line_id.service_commission_source != 'from_parts':
            return True
        values, missing = self._derived_commission_values()
        if missing:
            return False
        Model = self.env['wof.film.parts.commission.lines']
        existing = self.part_line_id.commission_line_ids
        desired = {size.id if size else False for size, amount in values}
        existing.filtered(lambda line: (line.car_size_id.id if line.car_size_id else False) not in desired).unlink()
        for size, amount in values:
            target = existing.filtered(lambda line: line.car_size_id == size)[:1] if size else existing.filtered(lambda line: not line.car_size_id)[:1]
            vals = {'part_line_id': self.part_line_id.id, 'car_size_id': size.id if size else False, 'commission': amount}
            target.write(vals) if target else Model.create(vals)
        return True

    @api.depends(
        'part_line_id.price_line_ids.car_size_id', 'part_line_id.price_line_ids.free_part',
        'part_line_id.commission_line_ids.car_size_id',
        'part_line_id.service_commission_source', 'part_line_id.technician_commission_distribution',
        'part_line_id.commission_calculation_policy',
        'wizard_id.pricing_policy', 'wizard_id.commission_calculation_policy',
        'wizard_id.film_id.car_size_ids', 'car_part_id.service_area_part_ids',
    )
    def _compute_completion(self):
        for rec in self:
            sizes = rec.wizard_id.film_id.car_size_ids
            price_lines = rec.part_line_id.price_line_ids
            commission_lines = rec.part_line_id.commission_line_ids
            if rec.wizard_id.pricing_policy == 'by_size':
                required = set(sizes.ids)
                configured_lines = price_lines.filtered(lambda l: l.car_size_id and l.car_size_id.id in required)
                configured = set(configured_lines.mapped('car_size_id').ids)
                free_sizes = set(configured_lines.filtered('free_part').mapped('car_size_id').ids)
                rec.price_missing_count = len(required - configured)
                rec.price_complete = bool(required) and not rec.price_missing_count
                rec.price_is_free = bool(required) and configured == required and free_sizes == required
                if rec.price_is_free:
                    rec.price_summary = 'جميع الأحجام مجانية'
                elif rec.price_complete:
                    paid_count = len(required - free_sizes)
                    rec.price_summary = '%s مدفوعة · %s مجانية' % (paid_count, len(free_sizes)) if free_sizes else '%s/%s أسعار مكتملة' % (len(configured), len(required))
                else:
                    rec.price_summary = '%s/%s أسعار مكتملة' % (len(configured), len(required))
            else:
                default_line = price_lines.filtered(lambda line: not line.car_size_id)[:1]
                rec.price_is_free = bool(default_line and default_line.free_part)
                rec.price_missing_count = 0 if default_line else 1
                rec.price_complete = bool(default_line)
                rec.price_summary = ('مجاني — لا يتطلب سعرًا' if rec.price_is_free else ('سعر موحد محفوظ' if default_line else 'السعر الموحد غير مدخل'))

            rec.derived_commission_details = ''
            if rec.part_type == 'service_area' and rec.part_line_id.service_commission_source == 'from_parts':
                values, missing = rec._derived_commission_values()
                rec.commission_missing_count = len(missing)
                rec.commission_complete = not missing and bool(values)
                if missing:
                    rec.commission_summary = 'تحتاج عمولات الأجزاء: %s' % '، '.join(missing)
                else:
                    rec.commission_summary = 'محسوبة تلقائيًا من عمولات الأجزاء'
                    rec.derived_commission_details = ' | '.join(
                        ('%s: %.2f' % (size.name, amount)) if size else ('الإجمالي: %.2f' % amount)
                        for size, amount in values
                    )
            elif (rec.part_line_id.commission_calculation_policy or rec.wizard_id.commission_calculation_policy) == 'by_size':
                configured = set(commission_lines.filtered('car_size_id').mapped('car_size_id').ids)
                required = set(sizes.ids)
                rec.commission_missing_count = len(required - configured)
                rec.commission_complete = bool(required) and not rec.commission_missing_count
                rec.commission_summary = '%s/%s عمولات' % (len(required & configured), len(required))
            else:
                ok = bool(commission_lines.filtered(lambda line: not line.car_size_id))
                rec.commission_missing_count = 0 if ok else 1
                rec.commission_complete = ok
                rec.commission_summary = 'عمولة موحدة محفوظة' if ok else 'العمولة الموحدة غير مدخلة'

    def action_toggle_price(self):
        self.ensure_one(); self.price_expanded = not self.price_expanded
        return self.wizard_id._dialog_action()

    def action_toggle_commission(self):
        self.ensure_one(); self.commission_expanded = not self.commission_expanded
        return self.wizard_id._dialog_action()

    def _open_value_dialog(self, mode):
        self.ensure_one()
        dialog = self.env['wof.film.setup.value.dialog'].create({
            'wizard_id': self.wizard_id.id, 'commercial_line_id': self.id, 'mode': mode,
        })
        dialog._prepare_entries()
        return dialog._dialog_action()

    def action_edit_price(self):
        return self._open_value_dialog('price')

    def action_edit_commission(self):
        return self._open_value_dialog('commission')


class WofFilmSetupValueDialog(models.TransientModel):
    _name = 'wof.film.setup.value.dialog'
    _description = 'إدخال أسعار أو عمولات مكوّن الفيلم'

    wizard_id = fields.Many2one('wof.film.setup.wizard', required=True, ondelete='cascade', readonly=True)
    commercial_line_id = fields.Many2one('wof.film.setup.commercial.line', required=True, ondelete='cascade', readonly=True)
    mode = fields.Selection([('price', 'التسعير'), ('commission', 'العمولة')], required=True, readonly=True)
    pricing_policy = fields.Selection(related='wizard_id.pricing_policy', readonly=True)
    commission_policy = fields.Selection([('fixed', 'عمولة موحدة'), ('by_size', 'حسب حجم السيارة')], string='طريقة احتساب العمولة', default='fixed', required=True)
    initial_commission_policy = fields.Selection([('fixed', 'عمولة موحدة'), ('by_size', 'حسب حجم السيارة')], readonly=True)
    source_uniform_commission_value = fields.Float(readonly=True)
    part_name = fields.Char(related='commercial_line_id.part_name', readonly=True)
    part_type = fields.Selection(related='commercial_line_id.part_type', readonly=True)
    child_names = fields.Char(related='commercial_line_id.child_names', readonly=True)
    currency_id = fields.Many2one(related='wizard_id.company_id.currency_id', readonly=True)
    entry_ids = fields.One2many('wof.film.setup.value.entry', 'dialog_id', string='القيم')
    price_charge_mode = fields.Selection(
        [('paid', 'مدفوع'), ('free', 'مجاني')], string='نوع التسعير', default='paid', required=True,
    )
    pricing_application_mode = fields.Selection([
        ('per_size', 'سعر مستقل لكل حجم'),
        ('uniform', 'نفس السعر لكل الأحجام'),
        ('all_free', 'مجاني لكل الأحجام'),
    ], string='طريقة تطبيق السعر على الأحجام', default='per_size', required=True)
    uniform_price = fields.Monetary(string='السعر الموحد لجميع الأحجام', currency_field='currency_id')
    uniform_price_readonly = fields.Boolean(string='للقراءة فقط')
    service_commission_source = fields.Selection(
        [('independent', 'عمولة مستقلة لمنطقة الخدمة'), ('from_parts', 'حسب عمولات مكونات المنطقة')],
        string='مصدر عمولة منطقة الخدمة', default='independent', required=True,
    )
    commission_value_type = fields.Selection(
        [('fixed', 'مبلغ ثابت'), ('percent', 'نسبة مئوية')],
        string='نوع العمولة', default='fixed', required=True,
    )
    commission_readonly = fields.Boolean(string='للقراءة فقط')
    uniform_commission_value = fields.Float(string='قيمة العمولة الموحدة')
    commission_size_names = fields.Char(string='أحجام السيارات', compute='_compute_commission_size_names')
    technician_commission_distribution = fields.Selection(
        [('equal', 'بالتساوي بين الفنيين'),
         ('by_technician_ratio', 'حسب نسبة الفني'),
         ('by_part', 'حسب عمولة الجزء المنفذ')],
        string='توزيع العمولة على الفنيين', default='equal', required=True,
    )
    technician_distribution_simple = fields.Selection(
        [('equal', 'بالتساوي بين الفنيين'), ('by_technician_ratio', 'حسب نسبة الفني')],
        string='توزيع العمولة على الفنيين', default='equal', required=True,
    )
    service_technician_distribution = fields.Selection(
        [('equal', 'بالتساوي بين الفنيين'), ('by_part', 'حسب عمولة الجزء المنفذ')],
        string='توزيع عمولة منطقة الخدمة', default='equal', required=True,
    )
    derived_commission_details = fields.Char(string='تفاصيل العمولة المحسوبة', readonly=True)

    @api.depends('wizard_id.film_id.car_size_ids')
    def _compute_commission_size_names(self):
        for dialog in self:
            dialog.commission_size_names = '، '.join(dialog.wizard_id.film_id.car_size_ids.mapped('name'))

    def _dialog_action(self):
        self.ensure_one()
        view = self.env.ref('yousentech_wo_v4.view_wof_film_setup_value_dialog_form')
        return {
            'type': 'ir.actions.act_window',
            'name': _('تسعير %s') % self.part_name if self.mode == 'price' else _('عمولة %s') % self.part_name,
            'res_model': self._name, 'res_id': self.id, 'view_mode': 'form',
            'views': [(view.id, 'form')], 'target': 'new', 'context': dict(self.env.context),
        }

    def _prepare_entries(self):
        self.ensure_one()
        self.entry_ids.unlink()
        part_line = self.commercial_line_id.part_line_id
        if self.mode == 'price':
            self.price_charge_mode = 'paid'
            # Keep the detailed per-size mode as the safe default. If all saved
            # size rows already share one state/value, reopen in the compact mode.
            existing_prices = part_line.price_line_ids
            if self.pricing_policy == 'by_size' and existing_prices:
                expected = self.wizard_id.film_id.car_size_ids
                saved = existing_prices.filtered(lambda l: l.car_size_id in expected)
                if expected and len(saved) == len(expected) and all(saved.mapped('free_part')):
                    self.pricing_application_mode = 'all_free'
                elif expected and len(saved) == len(expected) and not any(saved.mapped('free_part')):
                    amounts = {round(v, 6) for v in saved.mapped('part_price')}
                    ro = set(saved.mapped('price_readonly'))
                    if len(amounts) == 1 and len(ro) == 1:
                        self.pricing_application_mode = 'uniform'
                        self.uniform_price = saved[0].part_price
                        self.uniform_price_readonly = saved[0].price_readonly
            else:
                self.pricing_application_mode = 'per_size'
        if self.mode == 'commission':
            self.commission_policy = part_line.commission_calculation_policy or self.wizard_id.commission_calculation_policy or 'fixed'
            self.initial_commission_policy = self.commission_policy
            default_commission_line = part_line.commission_line_ids.filtered(lambda line: not line.car_size_id)[:1]
            self.source_uniform_commission_value = default_commission_line.commission if default_commission_line else 0.0
            self.commission_value_type = part_line.commission_value_type or 'fixed'
            self.commission_readonly = bool(part_line.commission_readonly)
            self.technician_commission_distribution = part_line.technician_commission_distribution or 'equal'
            self.technician_distribution_simple = (
                part_line.technician_commission_distribution
                if part_line.technician_commission_distribution in ('equal', 'by_technician_ratio') else 'equal'
            )
            self.service_technician_distribution = (
                part_line.technician_commission_distribution
                if part_line.technician_commission_distribution in ('equal', 'by_part') else 'equal'
            )
        if self.mode == 'commission' and self.part_type == 'service_area':
            self.service_commission_source = part_line.service_commission_source or 'independent'
            if self.service_commission_source == 'from_parts':
                self.technician_commission_distribution = 'by_part'
                values, missing = self.commercial_line_id._derived_commission_values()
                self.derived_commission_details = (
                    ' | '.join((('%s: %.2f' % (size.name, amount)) if size else ('الإجمالي: %.2f' % amount)) for size, amount in values)
                    if not missing else 'ناقص إعداد: %s' % '، '.join(missing)
                )
                return
        policy = self.pricing_policy if self.mode == 'price' else self.commission_policy
        existing = part_line.price_line_ids if self.mode == 'price' else part_line.commission_line_ids
        sizes = self.wizard_id.film_id.car_size_ids if policy == 'by_size' else self.env['wof.car.size']
        targets = sizes if policy == 'by_size' else [False]
        values = []
        for seq, size in enumerate(targets, start=1):
            found = existing.filtered(lambda line: line.car_size_id == size)[:1] if size else existing.filtered(lambda line: not line.car_size_id)[:1]
            amount = (found.part_price if self.mode == 'price' else found.commission) if found else 0.0
            values.append({'dialog_id': self.id, 'sequence': seq * 10,
                           'car_size_id': size.id if size else False,
                           'label': size.name if size else (_('السعر الموحد') if self.mode == 'price' else _('العمولة الموحدة')),
                           'amount': amount if self.mode == 'price' else 0.0,
                           'commission_value': amount if self.mode == 'commission' else 0.0,
                           'is_free': bool(found.free_part) if (self.mode == 'price' and found) else False,
                           'price_readonly': bool(found.price_readonly) if (self.mode == 'price' and found) else False})
        if values:
            self.env['wof.film.setup.value.entry'].create(values)
        if self.mode == 'commission' and policy == 'fixed':
            first = self.entry_ids[:1]
            self.uniform_commission_value = first.commission_value if first else 0.0

    @api.onchange('commission_policy')
    def _onchange_commission_policy(self):
        """Rebuild commission rows when switching fixed <-> by-size.

        The conversion must preserve the currently saved uniform commission as
        the initial value for every vehicle size.  Keeping this transition in a
        dedicated onchange avoids a second generic onchange rebuilding the rows
        with zero values before the dialog is saved.
        """
        if self.mode != 'commission' or not self.commercial_line_id:
            return
        existing = self.commercial_line_id.part_line_id.commission_line_ids
        if self.commission_policy == 'by_size':
            default_line = existing.filtered(lambda line: not line.car_size_id)[:1]
            fallback = (default_line.commission if default_line else self.source_uniform_commission_value) or 0.0
            commands = [(5, 0, 0)]
            for seq, size in enumerate(self.wizard_id.film_id.car_size_ids, start=1):
                found = existing.filtered(lambda line: line.car_size_id == size)[:1]
                commands.append((0, 0, {
                    'sequence': seq * 10,
                    'car_size_id': size.id,
                    'label': size.name,
                    'commission_value': found.commission if found else fallback,
                    'amount': 0.0,
                }))
            self.entry_ids = commands
        else:
            default_line = existing.filtered(lambda line: not line.car_size_id)[:1]
            if default_line:
                value = default_line.commission
            elif self.entry_ids:
                # When returning from by-size to fixed, use the first current
                # size value as a predictable starting point; the user can edit it.
                value = self.entry_ids[:1].commission_value
            else:
                value = self.source_uniform_commission_value or 0.0
            self.uniform_commission_value = value
            self.entry_ids = [(5, 0, 0), (0, 0, {
                'sequence': 10,
                'label': _('العمولة الموحدة'),
                'commission_value': value,
                'amount': 0.0,
            })]

    @api.onchange('price_charge_mode', 'service_commission_source', 'pricing_application_mode', 'uniform_price', 'uniform_price_readonly', 'uniform_commission_value', 'commission_value_type')
    def _onchange_commercial_modes(self):
        if self.mode == 'price':
            if self.pricing_application_mode == 'all_free':
                self.uniform_price = 0.0
                self.uniform_price_readonly = False
                for entry in self.entry_ids:
                    entry.is_free = True
                    entry.amount = 0.0
                    entry.price_readonly = False
            elif self.pricing_application_mode == 'uniform':
                for entry in self.entry_ids:
                    entry.is_free = False
                    entry.amount = self.uniform_price or 0.0
                    entry.price_readonly = bool(self.uniform_price_readonly)
            elif self.pricing_application_mode == 'per_size':
                # Leaving "free for all sizes" must start the detailed mode
                # with normal editable size rows.  Do not carry the global-free
                # state into each individual vehicle size.
                for entry in self.entry_ids:
                    entry.is_free = False
                    entry.price_readonly = False
        if self.mode == 'commission' and self.commission_policy == 'fixed' and self.entry_ids:
            self.entry_ids[0].commission_value = self.uniform_commission_value or 0.0
        if self.mode == 'commission' and self.service_commission_source == 'from_parts':
            self.technician_commission_distribution = 'by_part'
            self.service_technician_distribution = 'by_part'
            if self.commercial_line_id:
                values, missing = self.commercial_line_id._derived_commission_values()
                self.derived_commission_details = (' | '.join((('%s: %.2f' % (s.name, a)) if s else ('الإجمالي: %.2f' % a)) for s, a in values)
                                                   if not missing else 'ناقص إعداد: %s' % '، '.join(missing))
        elif self.mode == 'commission' and self.part_type == 'service_area' and not self.entry_ids:
            # Switching from automatic child-based commission back to an
            # independent commission must immediately restore editable values.
            policy = self.commission_policy
            existing = self.commercial_line_id.part_line_id.commission_line_ids
            sizes = self.wizard_id.film_id.car_size_ids if policy == 'by_size' else self.env['wof.car.size']
            targets = sizes if policy == 'by_size' else [False]
            self.entry_ids = [(0, 0, {
                'sequence': seq * 10,
                'car_size_id': size.id if size else False,
                'label': size.name if size else _('العمولة الموحدة'),
                'amount': 0.0,
                'commission_value': ((existing.filtered(lambda line: line.car_size_id == size)[:1].commission if existing.filtered(lambda line: line.car_size_id == size)[:1] else 0.0) if size else (existing.filtered(lambda line: not line.car_size_id)[:1].commission if existing.filtered(lambda line: not line.car_size_id)[:1] else 0.0)),
            }) for seq, size in enumerate(targets, start=1)]

    def action_save(self):
        self.ensure_one()
        part_line = self.commercial_line_id.part_line_id
        if self.mode == 'commission':
            distribution = (
                self.service_technician_distribution if self.part_type == 'service_area'
                else self.technician_distribution_simple
            )

            # RC56: switching FIXED -> BY SIZE is a real data conversion, not
            # merely a UI onchange.  Odoo's editable one2many can display the
            # seeded uniform value in newly-created virtual rows without always
            # persisting untouched values back to the transient rows before the
            # object button calls action_save().  In that case the server sees
            # 0.0 although the user saw the old uniform commission on screen.
            #
            # Preserve the fixed commission as the seed for every size at save
            # time too.  This deliberately runs before the persistent policy is
            # changed so the transition is deterministic and survives a client
            # that omits untouched one2many values.
            converting_fixed_to_by_size = (
                self.initial_commission_policy == 'fixed'
                and self.commission_policy == 'by_size'
            )
            if converting_fixed_to_by_size:
                seed = self.source_uniform_commission_value
                if not seed:
                    default_line = part_line.commission_line_ids.filtered(lambda line: not line.car_size_id)[:1]
                    seed = default_line.commission if default_line else 0.0
                if seed:
                    # A zero received for a size during this transition means
                    # the seeded value was not posted by the web client.  Keep
                    # the inherited value.  Non-zero values explicitly edited
                    # by the user are preserved as entered.
                    for entry in self.entry_ids.filtered('car_size_id'):
                        if not entry.commission_value:
                            entry.commission_value = seed

            part_line.write({
                'commission_calculation_policy': self.commission_policy or self.wizard_id.commission_calculation_policy or 'fixed',
                'commission_value_type': self.commission_value_type or 'fixed',
                'commission_readonly': bool(self.commission_readonly),
                'technician_commission_distribution': distribution,
            })
            if self.commission_policy == 'fixed' and self.entry_ids:
                self.entry_ids[0].commission_value = self.uniform_commission_value or 0.0
        if self.mode == 'commission' and self.part_type == 'service_area':
            part_line.write({
                'service_commission_source': self.service_commission_source,
                'technician_commission_distribution': ('by_part' if self.service_commission_source == 'from_parts' else self.service_technician_distribution),
            })
            if self.service_commission_source == 'from_parts':
                self.commercial_line_id._ensure_commission_basis_lines()
                # It is valid to save this policy before child commissions are
                # complete. The stage will reveal those child rows and keep the
                # area marked as incomplete until they are configured.
                self.commercial_line_id._sync_commission_from_children()
                self.commercial_line_id.commission_expanded = True
                self.wizard_id.commercial_line_ids.invalidate_recordset()
                return self.wizard_id._dialog_action()

        if self.mode == 'price' and self.pricing_policy == 'by_size':
            if self.pricing_application_mode == 'all_free':
                for entry in self.entry_ids:
                    entry.is_free = True; entry.amount = 0.0; entry.price_readonly = False
            elif self.pricing_application_mode == 'uniform':
                if self.uniform_price < 0:
                    raise ValidationError(_('السعر لا يمكن أن يكون سالبًا.'))
                for entry in self.entry_ids:
                    entry.is_free = False; entry.amount = self.uniform_price; entry.price_readonly = bool(self.uniform_price_readonly)
        if not self.entry_ids:
            raise ValidationError(_('لا توجد قيم متاحة للحفظ.'))
        if any((entry.amount if self.mode == 'price' else entry.commission_value) < 0 for entry in self.entry_ids):
            raise ValidationError(_('القيمة لا يمكن أن تكون سالبة.'))
        if self.mode == 'commission' and self.commission_value_type == 'percent' and any(entry.commission_value > 100 for entry in self.entry_ids):
            raise ValidationError(_('نسبة العمولة يجب أن تكون بين 0 و100.'))
        if self.mode == 'price':
            Model = self.env['wof.film.parts.price.lines']; existing = part_line.price_line_ids
        else:
            Model = self.env['wof.film.parts.commission.lines']; existing = part_line.commission_line_ids
        desired_size_ids = set(self.entry_ids.filtered('car_size_id').mapped('car_size_id').ids)
        wants_default = bool(self.entry_ids.filtered(lambda e: not e.car_size_id))
        obsolete = existing.filtered(lambda line: (bool(line.car_size_id) and line.car_size_id.id not in desired_size_ids) or (not line.car_size_id and not wants_default))
        if obsolete:
            obsolete.unlink()

        # IMPORTANT: ``existing`` may still contain records just removed by
        # ``obsolete.unlink()``. Reusing that stale recordset can make the next
        # ``target.write()`` hit a deleted commission/price line and Odoo raises
        # MissingError ("Record does not exist or has been deleted").
        # Reload only records that still exist before doing the upsert loop.
        existing = Model.search([('part_line_id', '=', part_line.id)])

        tax = self.wizard_id.film_id.tax_id if self.wizard_id.film_id.tax_enabled else self.env['account.tax']
        for entry in self.entry_ids:
            target = existing.filtered(lambda line: line.car_size_id == entry.car_size_id)[:1] if entry.car_size_id else existing.filtered(lambda line: not line.car_size_id)[:1]
            vals = {'part_line_id': part_line.id, 'car_size_id': entry.car_size_id.id if entry.car_size_id else False}
            if self.mode == 'price':
                is_free = bool(entry.is_free)
                vals.update({
                    'part_price': 0.0 if is_free else entry.amount,
                    'tax_id': False if is_free else (tax.id if tax else False),
                    'free_part': is_free,
                    'price_readonly': False if is_free else bool(entry.price_readonly),
                })
            else:
                vals.update({'commission': entry.commission_value})
            if target:
                target.write(vals)
            else:
                created = Model.create(vals)
                existing |= created
        if self.mode == 'price': self.commercial_line_id.price_expanded = True
        else: self.commercial_line_id.commission_expanded = True
        self.wizard_id.commercial_line_ids.invalidate_recordset()
        return self.wizard_id._dialog_action()


class WofFilmSetupValueEntry(models.TransientModel):
    _name = 'wof.film.setup.value.entry'
    _description = 'قيمة سعر أو عمولة في معالج الفيلم'
    _order = 'sequence, id'

    dialog_id = fields.Many2one('wof.film.setup.value.dialog', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10, readonly=True)
    car_size_id = fields.Many2one('wof.car.size', string='حجم السيارة', readonly=True)
    label = fields.Char(string='الحجم / السياسة', readonly=True)
    currency_id = fields.Many2one(related='dialog_id.currency_id', readonly=True)
    amount = fields.Monetary(string='القيمة', currency_field='currency_id', required=True)
    commission_value = fields.Float(string='قيمة العمولة')
    is_free = fields.Boolean(string='مجاني')
    price_readonly = fields.Boolean(string='للقراءة فقط')

    @api.onchange('is_free')
    def _onchange_is_free(self):
        for entry in self:
            if entry.is_free:
                entry.amount = 0.0
                entry.price_readonly = False


class WofFilmSetupTintLine(models.TransientModel):
    _name = 'wof.film.setup.tint.line'
    _description = 'درجة لون في معالج تهيئة الفيلم'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'wof.film.setup.wizard', required=True, ondelete='cascade', index=True,
    )
    sequence = fields.Integer(default=10, readonly=True)
    value = fields.Char(string='درجة اللون', required=True, readonly=True)
    code = fields.Char(string='الكود', required=True, readonly=True)
    selected = fields.Boolean(string='مفعّلة', default=True)
    locked = fields.Boolean(compute='_compute_locked')

    @api.depends('wizard_id.tint_selection_mode')
    def _compute_locked(self):
        for line in self:
            line.locked = line.wizard_id.tint_selection_mode == 'all'

    def action_toggle_selected(self):
        self.ensure_one()
        if self.locked:
            return self.wizard_id._dialog_action()
        self.selected = not self.selected
        return self.wizard_id._dialog_action()
