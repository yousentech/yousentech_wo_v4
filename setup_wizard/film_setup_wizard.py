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
        return self._dialog_action()

    def action_back_tint(self):
        self.current_step = 'tint'
        return self._dialog_action()

    def action_cancel(self):
        if self.hub_id:
            self.hub_id._refresh_films()
            return self.hub_id._reopen_hub()
        return {'type': 'ir.actions.act_window_close'}


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
