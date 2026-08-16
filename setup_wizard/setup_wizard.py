# -*- coding: utf-8 -*-

import re
from datetime import timezone

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError
from psycopg2 import IntegrityError


SERVICE_OPTIONS = [
    ('tint', 'عزل حراري'),
    ('ppf', 'حماية PPF'),
    ('nano', 'نانو سيراميك'),
    ('upholstery', 'تنجيد'),
    ('floor_mats', 'أرضيات'),
    ('others', 'أخرى'),
]

SETUP_STEPS = [
    ('activity', 'نشاط المركز'),
    ('sizes', 'أحجام السيارات'),
    ('services', 'درجات اللون'),
    ('operations', 'التشغيل والفوترة'),
    ('review', 'المراجعة والجاهزية'),
]

ACTIVITY_FIELDS = {
    'tint': 'activity_tint',
    'ppf': 'activity_ppf',
    'nano': 'activity_nano',
    'upholstery': 'activity_upholstery',
    'floor_mats': 'activity_floor_mats',
    'others': 'activity_others',
}

TECHNICAL_CODE_RE = re.compile(r'^[A-Z0-9][A-Z0-9._-]*$')
SETUP_TRANSITION_TOKEN = object()

SETUP_ACTIVITY_TYPES = [
    ('tint', 'عزل حراري'),
    ('general', 'نشاط عام'),
]

TINT_NUMBERING_METHODS = [
    ('sequential', 'ترقيم تسلسلي'),
    ('percentage', 'ترقيم بالنسب'),
]

TINT_SHADE_DEFAULTS = {
    'sequential': [('00', 10), ('01', 20), ('02', 30), ('03', 40), ('04', 50)],
    'percentage': [('00', 10), ('30', 20), ('50', 30), ('75', 40), ('100', 50)],
}

OPERATION_FIELD_DEFAULTS = [
    ('plate', 'اللوحة', True, False, 10),
    ('vin', 'الشاصي', False, False, 20),
    ('mobile', 'الجوال', True, False, 30),
    ('manufacture_year', 'سنة الصنع', False, False, 40),
    ('color', 'اللون', False, False, 50),
    ('agency', 'الوكالة', False, False, 60),
    ('delivery_time', 'وقت التسليم', False, False, 70),
    ('odometer', 'العداد', False, True, 80),
    ('salesperson', 'المندوب', False, True, 90),
    ('technician', 'الفني', True, False, 100),
]

OPERATION_FIELD_KEYS = [(key, label) for key, label, _required, _hidden, _sequence in OPERATION_FIELD_DEFAULTS]


def _utc_iso(value):
    if not value:
        return None
    parsed = fields.Datetime.to_datetime(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.isoformat().replace('+00:00', 'Z')


class WofSetupTemplate(models.Model):
    _name = 'wof.setup.template'
    _description = 'قالب تهيئة خدمة'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    service_kind = fields.Selection(SERVICE_OPTIONS, required=True, index=True)
    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    default_film_name = fields.Char(string="اسم الفيلم الافتراضي", required=True)
    default_price = fields.Float(string="السعر المقترح")
    default_commission = fields.Float(string="عمولة الفني المقترحة")
    warranty_years = fields.Integer(string="سنوات الضمان", default=1)
    inventory_enabled = fields.Boolean(string="يستخدم المخزون")
    part_line_ids = fields.One2many(
        'wof.setup.template.part', 'template_id', string="الأجزاء المقترحة",
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('setup_template_kind_unique', 'unique(service_kind)',
         'يوجد قالب لهذا النشاط مسبقًا.'),
        ('setup_template_code_unique', 'unique(code)',
         'كود قالب الخدمة مستخدم مسبقًا.'),
        ('setup_template_price_nonnegative', 'check(default_price >= 0)',
         'السعر المقترح لا يمكن أن يكون سالبًا.'),
        ('setup_template_commission_nonnegative', 'check(default_commission >= 0)',
         'العمولة المقترحة لا يمكن أن تكون سالبة.'),
        ('setup_template_warranty_nonnegative', 'check(warranty_years >= 0)',
         'سنوات الضمان لا يمكن أن تكون سالبة.'),
    ]

class WofSetupTemplatePart(models.Model):
    _name = 'wof.setup.template.part'
    _description = 'جزء مقترح في قالب التهيئة'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    template_id = fields.Many2one(
        'wof.setup.template', required=True, ondelete='cascade', index=True,
    )
    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    price_ratio = fields.Float(
        string="نسبة الجزء من السعر الأساسي", default=1.0,
    )

    _sql_constraints = [
        ('setup_template_part_code_unique', 'unique(code)',
         'كود جزء قالب التهيئة مستخدم مسبقًا.'),
        ('setup_template_part_ratio_nonnegative', 'check(price_ratio >= 0)',
         'نسبة سعر الجزء لا يمكن أن تكون سالبة.'),
    ]


class WofCompanyProfile(models.Model):
    _name = 'wof.company.profile'
    _inherit = ['wof.api.mixin']
    _description = 'ملف تهيئة نظام العناية'
    _rec_name = 'company_id'
    _order = 'company_id'
    _check_company_auto = True

    company_id = fields.Many2one(
        'res.company', string="الشركة", required=True,
        default=lambda self: self.env.company, ondelete='cascade', index=True,
    )
    state = fields.Selection(
        [('draft', 'لم تبدأ'), ('in_progress', 'قيد التهيئة'), ('ready', 'جاهز للتشغيل')],
        string="حالة التهيئة", default='draft', required=True, index=True,
    )
    current_step = fields.Selection(
        SETUP_STEPS, string="الخطوة الحالية", default='activity', required=True,
    )
    progress = fields.Integer(compute='_compute_progress', store=True)
    setup_version = fields.Char(default='17.0.4', readonly=True)
    completed_at = fields.Datetime(readonly=True, copy=False)

    # Legacy activity flags are intentionally kept for backward compatibility.
    # The onboarding UI now uses activity_line_ids as the source of truth.
    activity_tint = fields.Boolean(string="العزل الحراري", default=True)
    activity_ppf = fields.Boolean(string="حماية PPF", default=False)
    activity_nano = fields.Boolean(string="نانو سيراميك", default=False)
    activity_upholstery = fields.Boolean(string="التنجيد", default=False)
    activity_floor_mats = fields.Boolean(string="الأرضيات", default=False)
    activity_others = fields.Boolean(string="خدمات أخرى", default=False)

    activity_line_ids = fields.One2many(
        'wof.setup.activity.line', 'profile_id', string="أنشطة المنشأة", copy=True,
    )
    size_line_ids = fields.One2many(
        'wof.setup.size.line', 'profile_id', string="أحجام السيارات", copy=True,
    )
    tint_numbering_method = fields.Selection(
        TINT_NUMBERING_METHODS, string="طريقة ترقيم درجات اللون",
        default='sequential', required=True,
    )
    tint_shade_line_ids = fields.One2many(
        'wof.setup.tint.shade.line', 'profile_id',
        string="درجات اللون المعتمدة", copy=True,
    )
    has_tint_activity = fields.Boolean(
        compute='_compute_has_tint_activity', string="يوجد نشاط عزل حراري",
    )
    operation_field_line_ids = fields.One2many(
        'wof.setup.operation.field.line', 'profile_id',
        string='الحقول الرئيسية', copy=True,
    )
    operation_tax_enabled = fields.Boolean(string='تطبيق الضريبة', default=True)
    operation_tax_id = fields.Many2one(
        'account.tax', string='الضريبة الافتراضية', check_company=True,
        domain="[('type_tax_use', '=', 'sale'), ('company_id', '=', company_id)]",
    )
    operation_price_input_mode = fields.Selection(
        [('excluded', 'السعر قبل الضريبة'), ('included', 'السعر شامل الضريبة')],
        string='طريقة إدخال السعر', default='excluded', required=True,
    )
    operation_pricing_policy = fields.Selection(
        [('fixed', 'سعر موحد'), ('by_size', 'حسب حجم السيارة')],
        string='سياسة التسعير الافتراضية', default='fixed', required=True,
    )
    operation_auto_invoice = fields.Boolean(
        string='إنشاء فاتورة تلقائيًا عند تأكيد أمر التركيب', default=False,
    )
    operation_allow_multiple_technicians = fields.Boolean(
        string='السماح بتعدد الفنيين', default=True,
    )
    operation_technician_required = fields.Boolean(string='الفني إجباري', default=True)
    service_line_ids = fields.One2many(
        'wof.setup.service.line', 'profile_id', string="الخدمات والأسعار", copy=True,
    )

    payment_policy = fields.Selection(
        [('partial', 'السماح بالدفع الجزئي'),
         ('full_before_invoice', 'يشترط اكتمال الدفع قبل الفاتورة')],
        default='partial', required=True,
    )
    discount_scope = fields.Selection(
        [('order', 'على إجمالي الأمر'), ('service', 'على كل خدمة')],
        default='order', required=True,
    )
    commission_event = fields.Selection(
        [('delivery', 'بعد إنجاز أمر التركيب'), ('invoice', 'بعد ترحيل الفاتورة')],
        default='delivery', required=True,
    )
    required_vehicle_data = fields.Selection(
        [('plate_mobile', 'اللوحة وجوال العميل'),
         ('plate_vin_mobile', 'اللوحة والشاصي وجوال العميل')],
        default='plate_mobile', required=True,
    )
    use_inventory = fields.Boolean(string="صرف المواد من المخزون", default=True)
    use_appointments = fields.Boolean(string="استخدام مواعيد التسليم", default=True)
    advanced_pricing = fields.Boolean(string="تسعير مختلف حسب حجم السيارة")
    advanced_commission = fields.Boolean(string="عمولة مختلفة حسب حجم السيارة")

    readiness_ok = fields.Boolean(compute='_compute_readiness')
    readiness_note = fields.Char(compute='_compute_readiness')
    service_count = fields.Integer(compute='_compute_dashboard')
    film_count = fields.Integer(compute='_compute_dashboard')
    size_count = fields.Integer(compute='_compute_dashboard')
    missing_price_count = fields.Integer(compute='_compute_dashboard')

    _sql_constraints = [
        ('company_profile_company_unique', 'unique(company_id)',
         'يوجد ملف تهيئة لهذه الشركة مسبقًا.'),
    ]

    def _ensure_can_configure(self):
        if not self.env.user.has_group(
            'yousentech_wo_v4.group_wo_settings'
        ):
            raise AccessError(_(
                'هذه العملية متاحة لمسؤول تهيئة نظام العناية فقط.'
            ))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            company = self.env['res.company'].browse(
                vals.get('company_id') or self.env.company.id
            ).exists()
            if not company or company not in self.env.companies:
                raise AccessError(_(
                    'لا يمكنك إنشاء ملف تهيئة لشركة غير مسموحة.'
                ))
            vals.update({
                'company_id': company.id,
                'state': 'draft',
                'current_step': 'activity',
                'completed_at': False,
                'setup_version': '17.0.4',
            })
        records = super().create(vals_list)
        for record in records:
            record._ensure_default_activities()
            record._ensure_default_sizes()
            record._ensure_default_tint_shades()
            record._ensure_default_operation_fields()
            record._ensure_default_operation_tax()
        return records

    def write(self, vals):
        tracked = {
            *ACTIVITY_FIELDS.values(),
            'activity_line_ids', 'size_line_ids', 'tint_numbering_method',
            'tint_shade_line_ids', 'operation_field_line_ids', 'service_line_ids',
            'operation_tax_enabled', 'operation_tax_id',
            'operation_price_input_mode', 'operation_pricing_policy',
            'operation_auto_invoice', 'operation_allow_multiple_technicians',
            'operation_technician_required',
            'payment_policy', 'discount_scope', 'commission_event',
            'required_vehicle_data', 'use_inventory', 'use_appointments',
            'advanced_pricing', 'advanced_commission',
        }
        if tracked.intersection(vals):
            self._ensure_can_configure()
        protected = {
            'company_id', 'state', 'current_step',
            'completed_at', 'setup_version',
        }
        if (
            protected.intersection(vals)
            and self.env.context.get('wof_setup_transition_token')
            is not SETUP_TRANSITION_TOKEN
        ):
            raise ValidationError(
                'غيّر حالة التهيئة من الأزرار المخصصة، وليس بالكتابة المباشرة.'
            )
        if 'tint_numbering_method' in vals and any(
            record.state == 'ready'
            and record.tint_numbering_method != vals['tint_numbering_method']
            for record in self
        ):
            raise ValidationError(
                'طريقة ترقيم درجات اللون مثبتة بعد تفعيل النظام ولا يمكن تغييرها.'
            )
        result = super().write(vals)
        changed = sorted(tracked.intersection(vals))
        if changed:
            for record in self:
                record._audit_event(
                    'setup.configuration.updated',
                    {'fields': changed},
                )
        return result

    def _write_setup_transition(self, vals):
        return self.with_context(
            wof_setup_transition_token=SETUP_TRANSITION_TOKEN
        ).write(vals)

    @api.model
    def get_or_create_for_company(self, company=None):
        company = company or self.env.company
        if company not in self.env.companies:
            raise AccessError(_('الشركة المطلوبة ليست ضمن الشركات المسموح لك بالعمل عليها.'))
        profile = self.search([('company_id', '=', company.id)], limit=1)
        if not profile:
            try:
                with self.env.cr.savepoint():
                    profile = self.with_company(company).create({
                        'company_id': company.id,
                    })
                    profile._audit_event('setup.profile.created')
            except IntegrityError:
                profile = self.search([
                    ('company_id', '=', company.id),
                ], limit=1)
                if not profile:
                    raise
        profile._ensure_default_activities()
        return profile

    @api.model
    def open_main_menu(self, company=None):
        company = company or self.env.company
        if company not in self.env.companies:
            raise AccessError(_('الشركة المطلوبة ليست ضمن الشركات المسموح لك بالعمل عليها.'))
        profile = self.search([('company_id', '=', company.id)], limit=1)
        can_configure = self.env.user.has_group(
            'yousentech_wo_v4.group_wo_settings'
        )
        if not profile:
            if not can_configure:
                raise AccessError(_(
                    'لم تبدأ تهيئة نظام العناية لهذه الشركة. '
                    'اطلب من مسؤول تهيئة النظام إكمالها أولًا.'
                ))
            profile = self.get_or_create_for_company(company)
        if profile.state != 'ready' and not can_configure:
            raise AccessError(_(
                'تهيئة نظام العناية لهذه الشركة غير مكتملة. '
                'اطلب من مسؤول التهيئة إكمالها.'
            ))
        if profile.state == 'ready':
            return self.env['wof.installation.order'].open_main_menu()
        return profile._wizard_action()

    @api.depends('current_step', 'state')
    def _compute_progress(self):
        values = {'activity': 20, 'sizes': 40, 'services': 60,
                  'operations': 80, 'review': 95}
        for record in self:
            record.progress = 100 if record.state == 'ready' else values[record.current_step]

    @api.depends('activity_line_ids.selected', 'activity_line_ids.activity_type')
    def _compute_has_tint_activity(self):
        for record in self:
            record.has_tint_activity = bool(record.activity_line_ids.filtered(
                lambda line: line.selected and line.activity_type == 'tint'
            ))

    @api.depends(
        'activity_line_ids.selected', 'activity_line_ids.name',
        'activity_tint', 'activity_ppf', 'activity_nano',
        'activity_upholstery', 'activity_floor_mats', 'activity_others',
        'size_line_ids.selected', 'tint_numbering_method',
        'tint_shade_line_ids.selected', 'tint_shade_line_ids.value',
        'service_line_ids.enabled', 'service_line_ids.base_price',
    )
    def _compute_readiness(self):
        for record in self:
            issues = record._readiness_issues()
            record.readiness_ok = not issues
            record.readiness_note = (
                'جاهز لتفعيل النظام'
                if not issues
                else '، '.join(issue['message'] for issue in issues)
            )

    def _readiness_issues(self):
        self.ensure_one()
        issues = []
        if not self._selected_activity_keys():
            issues.append({
                'code': 'SETUP_ACTIVITY_REQUIRED',
                'field': 'activities',
                'message': 'اختر نشاطًا واحدًا على الأقل',
            })
        if not self.size_line_ids.filtered('selected'):
            issues.append({
                'code': 'SETUP_SIZE_REQUIRED',
                'field': 'size_line_ids',
                'message': 'فعّل حجم سيارة واحدًا على الأقل',
            })
        if self.has_tint_activity:
            if not self.tint_numbering_method:
                issues.append({
                    'code': 'SETUP_TINT_METHOD_REQUIRED',
                    'field': 'tint_numbering_method',
                    'message': 'اختر طريقة ترقيم درجات اللون',
                })
            if not self.tint_shade_line_ids.filtered('selected'):
                issues.append({
                    'code': 'SETUP_TINT_SHADE_REQUIRED',
                    'field': 'tint_shade_line_ids',
                    'message': 'فعّل درجة لون واحدة على الأقل',
                })
        if self.operation_tax_enabled and not self.operation_tax_id:
            issues.append({
                'code': 'SETUP_OPERATION_TAX_REQUIRED',
                'field': 'operation_tax_id',
                'message': 'اختر الضريبة الافتراضية أو أوقف تطبيق الضريبة',
            })
        return issues

    def _setup_state_payload(self):
        self.ensure_one()
        return {
            'public_uuid': self.public_uuid,
            'company_uuid': self.company_id.wof_public_uuid,
            'state': self.state,
            'current_step': self.current_step,
            'progress': self.progress,
            'setup_version': self.setup_version,
            'updated_at': _utc_iso(self.write_date),
            'completed_at': _utc_iso(self.completed_at),
        }

    def validate_readiness(self):
        self.ensure_one()
        self._compute_readiness()
        return {
            'ready': self.readiness_ok,
            'message': self.readiness_note,
            'issues': self._readiness_issues(),
            'step': self.current_step,
            'progress': self.progress,
        }

    def _compute_dashboard(self):
        service_model = self.env['wof.service.type']
        film_model = self.env['wof.film.category']
        size_model = self.env['wof.car.size']
        price_model = self.env['wof.film.parts.price.lines']
        for record in self:
            domain = [('company_id', '=', record.company_id.id)]
            record.service_count = service_model.search_count(domain)
            record.film_count = film_model.search_count(domain)
            record.size_count = size_model.search_count(domain)
            record.missing_price_count = price_model.search_count(
                domain + [('part_price', '=', 0), ('free_part', '=', False)]
            )

    def _selected_activity_keys(self):
        """Compatibility bridge while the remaining setup stages are being redesigned.

        The new activity model has only two internal behaviors: heat insulation
        and general activity. Legacy setup templates still understand ``tint``
        and ``others``; this bridge keeps later, not-yet-redesigned stages safe
        without exposing the old activity taxonomy in Stage 1.
        """
        self.ensure_one()
        self._ensure_default_activities()
        selected = self.activity_line_ids.filtered('selected')
        keys = []
        if selected.filtered(lambda line: line.activity_type == 'tint'):
            keys.append('tint')
        if selected.filtered(lambda line: line.activity_type == 'general'):
            keys.append('others')
        return keys

    def _ensure_default_activities(self):
        self.ensure_one()
        existing_types = set(self.activity_line_ids.filtered('is_system_default').mapped('activity_type'))
        legacy_general_enabled = any([
            self.activity_ppf, self.activity_nano, self.activity_upholstery,
            self.activity_floor_mats, self.activity_others,
        ])
        defaults = [
            {
                'sequence': 10, 'activity_type': 'tint',
                'name': 'عزل حراري', 'selected': bool(self.activity_tint),
                'description': 'نشاط متخصص في أفلام العزل الحراري ودرجات اللون.',
            },
            {
                'sequence': 20, 'activity_type': 'general',
                'name': 'نشاط عام', 'selected': bool(legacy_general_enabled),
                'description': 'للـ PPF، النانو سيراميك، التلميع، الحماية والخدمات الأخرى.',
            },
        ]
        for vals in defaults:
            existing = self.activity_line_ids.filtered(
                lambda line: line.is_system_default and line.activity_type == vals['activity_type']
            )[:1]
            if not existing:
                self.env['wof.setup.activity.line'].create({
                    **vals, 'profile_id': self.id, 'is_system_default': True,
                })
            elif not existing.description:
                existing.write({'description': vals['description']})

    def _sync_legacy_activity_flags(self):
        """Keep the old flags coherent while later setup stages are migrated."""
        self.ensure_one()
        selected = self.activity_line_ids.filtered('selected')
        vals = {
            'activity_tint': bool(selected.filtered(lambda line: line.activity_type == 'tint')),
            'activity_others': bool(selected.filtered(lambda line: line.activity_type == 'general')),
            'activity_ppf': False,
            'activity_nano': False,
            'activity_upholstery': False,
            'activity_floor_mats': False,
        }
        changed = {key: value for key, value in vals.items() if self[key] != value}
        if changed:
            self.write(changed)

    def action_edit_name(self):
        """Static-view compatibility proxy; activity cards call the child model method."""
        self.ensure_one()
        return self._wizard_action()

    def action_edit_size(self):
        """Static-view compatibility proxy; size cards call the child model method."""
        self.ensure_one()
        return self._wizard_action()

    def action_add_general_activity(self):
        """Open a lightweight dialog; do not create placeholder activity data."""
        self.ensure_one()
        self._ensure_can_configure()
        self._ensure_default_activities()
        dialog = self.env['wof.setup.activity.dialog'].create({
            'mode': 'add',
            'profile_id': self.id,
            'name': False,
            'description': False,
        })
        return dialog._dialog_action()

    def _ensure_default_sizes(self):
        """Keep the center-size master draft complete without overwriting user choices.

        Stage 2 uses these lines directly as the official setup draft.  Existing
        installations may still have the old feminine Arabic labels from the
        legacy tree view; only those untouched legacy labels are normalized.
        User-renamed sizes are never overwritten.
        """
        self.ensure_one()
        defaults = [
            (10, 'SMALL', 'صغير', {'صغيرة'}),
            (20, 'MEDIUM', 'متوسط', {'متوسطة'}),
            (30, 'LARGE', 'كبير', {'كبيرة'}),
            (40, 'SUV', 'SUV', set()),
        ]
        lines_by_code = {line.code: line for line in self.size_line_ids}
        for sequence, code, name, legacy_names in defaults:
            line = lines_by_code.get(code)
            if not line:
                self.env['wof.setup.size.line'].create({
                    'profile_id': self.id,
                    'sequence': sequence,
                    'code': code,
                    'name': name,
                    'selected': True,
                    'is_system_default': True,
                })
                continue
            vals = {}
            if line.name in legacy_names:
                vals['name'] = name
            if not line.sequence:
                vals['sequence'] = sequence
            if not line.is_system_default and code in {'SMALL', 'MEDIUM', 'LARGE', 'SUV'}:
                vals['is_system_default'] = True
            if vals:
                line.write(vals)

    def action_add_car_size(self):
        """Open the Stage 2 size dialog without creating placeholder rows."""
        self.ensure_one()
        self._ensure_can_configure()
        self._ensure_default_sizes()
        dialog = self.env['wof.setup.size.dialog'].create({
            'mode': 'add',
            'profile_id': self.id,
            'name': False,
        })
        return dialog._dialog_action()

    def _ensure_default_operation_fields(self):
        self.ensure_one()
        existing = {line.field_key: line for line in self.operation_field_line_ids}
        for key, label, required, hidden, sequence in OPERATION_FIELD_DEFAULTS:
            line = existing.get(key)
            vals = {
                'label': label,
                'sequence': sequence,
            }
            if not line:
                vals.update({
                    'profile_id': self.id,
                    'field_key': key,
                    'required': required and not hidden,
                    'hidden': hidden,
                })
                self.env['wof.setup.operation.field.line'].create(vals)
            elif not line.label:
                line.with_context(wof_operation_setup_sync=True).write(vals)
        return True

    def _ensure_default_operation_tax(self):
        self.ensure_one()
        if self.operation_tax_id:
            return True
        tax = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('company_id', '=', self.company_id.id),
            ('amount_type', '=', 'percent'),
            ('amount', '=', 15),
            ('active', '=', True),
        ], limit=1)
        if not tax:
            tax = self.env['account.tax'].search([
                ('type_tax_use', '=', 'sale'),
                ('company_id', '=', self.company_id.id),
                ('active', '=', True),
            ], limit=1)
        if tax:
            super(WofCompanyProfile, self).write({'operation_tax_id': tax.id})
        return True

    def _sync_operation_compatibility(self):
        """Keep legacy setup fields aligned while Stage 4 is migrated."""
        self.ensure_one()
        policies = {line.field_key: line for line in self.operation_field_line_ids}
        plate = policies.get('plate')
        vin = policies.get('vin')
        mobile = policies.get('mobile')
        vals = {
            'required_vehicle_data': (
                'plate_vin_mobile'
                if vin and vin.required and not vin.hidden
                else 'plate_mobile'
            ),
            'advanced_pricing': self.operation_pricing_policy == 'by_size',
        }
        # Legacy validation historically requires plate/mobile. Preserve it unless
        # a later runtime screen explicitly migrates to per-field policies.
        if plate and plate.hidden:
            plate.with_context(wof_operation_setup_sync=True).write({'required': False})
        if mobile and mobile.hidden:
            mobile.with_context(wof_operation_setup_sync=True).write({'required': False})
        super(WofCompanyProfile, self).write(vals)
        return True

    def _ensure_default_tint_shades(self):
        self.ensure_one()
        method = self.tint_numbering_method or 'sequential'
        expected = TINT_SHADE_DEFAULTS[method]
        existing = {line.value: line for line in self.tint_shade_line_ids}
        if self.tint_shade_line_ids and any(
            line.numbering_method != method for line in self.tint_shade_line_ids
        ):
            self.tint_shade_line_ids.unlink()
            existing = {}
        for value, sequence in expected:
            line = existing.get(value)
            vals = {
                'profile_id': self.id,
                'numbering_method': method,
                'value': value,
                'code': ('SEQ-' if method == 'sequential' else 'PCT-') + value,
                'sequence': sequence,
                'selected': True,
            }
            if line:
                updates = {k: v for k, v in vals.items() if k != 'profile_id' and line[k] != v}
                if updates:
                    line.with_context(wof_tint_setup_sync=True).write(updates)
            else:
                self.env['wof.setup.tint.shade.line'].create(vals)

    def _set_tint_numbering_method(self, method):
        self.ensure_one()
        self._ensure_can_configure()
        if self.state == 'ready':
            raise ValidationError(
                'طريقة ترقيم درجات اللون مثبتة بعد تفعيل النظام ولا يمكن تغييرها.'
            )
        if method not in dict(TINT_NUMBERING_METHODS):
            raise ValidationError(_('طريقة ترقيم درجات اللون غير صحيحة.'))
        if self.tint_numbering_method != method:
            self.tint_shade_line_ids.unlink()
            self.write({'tint_numbering_method': method})
        self._ensure_default_tint_shades()
        return self._wizard_action()

    def action_set_tint_numbering_sequential(self):
        return self._set_tint_numbering_method('sequential')

    def action_set_tint_numbering_percentage(self):
        return self._set_tint_numbering_method('percentage')

    def _apply_tint_degrees(self):
        self.ensure_one()
        Degree = self.env['wof.tint.degree'].with_context(active_test=False)
        if not self.has_tint_activity:
            Degree.search([
                ('company_id', '=', self.company_id.id),
                ('is_setup_default', '=', True),
            ]).write({'active': False})
            return
        selected = self.tint_shade_line_ids.filtered('selected')
        selected_values = set(selected.mapped('value'))
        Degree.search([
            ('company_id', '=', self.company_id.id),
            ('is_setup_default', '=', True),
            ('value', 'not in', list(selected_values)),
        ]).write({'active': False})
        for line in selected:
            degree = Degree.search([
                ('company_id', '=', self.company_id.id),
                ('value', '=', line.value),
            ], limit=1)
            vals = {
                'company_id': self.company_id.id,
                'sequence': line.sequence,
                'value': line.value,
                'code': line.code,
                'numbering_method': self.tint_numbering_method,
                'is_setup_default': True,
                'active': True,
            }
            if degree:
                degree.write(vals)
            else:
                Degree.create(vals)

    def _sync_service_drafts(self):
        self.ensure_one()
        selected = set(self._selected_activity_keys())
        templates = self.env['wof.setup.template'].search([
            ('service_kind', 'in', list(selected)), ('active', '=', True),
        ])
        missing = selected.difference(templates.mapped('service_kind'))
        if missing:
            raise ValidationError(_(
                'قوالب التهيئة التالية غير موجودة أو مؤرشفة: %s. '
                'حدّث الموديول أو راجع مسؤول النظام قبل المتابعة.'
            ) % ', '.join(sorted(missing)))
        lines = {line.service_kind: line for line in self.service_line_ids}
        for template in templates:
            vals = {
                'enabled': True, 'name': template.name, 'code': template.code,
                'film_name': template.default_film_name,
                'base_price': template.default_price,
                'default_commission': template.default_commission,
                'warranty_years': template.warranty_years,
                'inventory_enabled': template.inventory_enabled,
                'template_id': template.id,
            }
            line = lines.get(template.service_kind)
            if line:
                if not line.user_modified:
                    line.with_context(template_sync=True).write(vals)
                else:
                    line.enabled = True
            else:
                vals.update({
                    'profile_id': self.id, 'service_kind': template.service_kind,
                })
                self.env['wof.setup.service.line'].create(vals)
        self.service_line_ids.filtered(
            lambda line: line.service_kind not in selected
        ).write({'enabled': False})

    def _wizard_action(self):
        self.ensure_one()
        self._ensure_default_activities()
        self._ensure_default_sizes()
        self._ensure_default_tint_shades()
        self._ensure_default_operation_fields()
        if self.current_step in ('operations', 'review'):
            self._ensure_default_operation_tax()
        return {
            'type': 'ir.actions.act_window', 'name': _('مركز تهيئة النظام'),
            'res_model': 'wof.company.profile', 'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('yousentech_wo_v4.view_wof_setup_wizard_form').id,
            'target': 'new',
        }

    def action_start(self):
        self.ensure_one()
        self.start_or_resume_setup()
        return self._wizard_action()

    def action_save(self):
        self.ensure_one()
        self.save_setup_progress()
        return self._wizard_action()

    def start_or_resume_setup(self):
        self.ensure_one()
        self._ensure_can_configure()
        if self.state == 'draft':
            self._write_setup_transition({'state': 'in_progress'})
        return self._setup_state_payload()

    def save_setup_progress(self):
        self.ensure_one()
        self._ensure_can_configure()
        if self.state == 'draft':
            self._write_setup_transition({'state': 'in_progress'})
        return self._setup_state_payload()

    def advance_setup(self):
        self.ensure_one()
        self._ensure_can_configure()
        previous_step = self.current_step
        next_step = self.current_step
        if self.current_step == 'activity':
            if not self._selected_activity_keys():
                raise ValidationError(_('اختر نشاطًا واحدًا على الأقل قبل المتابعة.'))
            # Stage 1 only chooses center activities. It must not create films,
            # services, components, prices or commissions.
            next_step = 'sizes'
        elif self.current_step == 'sizes':
            if not self.size_line_ids.filtered('selected'):
                raise ValidationError(_('فعّل حجم سيارة واحدًا على الأقل قبل المتابعة.'))
            self._ensure_default_tint_shades()
            next_step = 'services'
        elif self.current_step == 'services':
            if self.has_tint_activity and not self.tint_shade_line_ids.filtered('selected'):
                raise ValidationError(_('فعّل درجة لون واحدة على الأقل قبل المتابعة.'))
            self._ensure_default_operation_fields()
            self._ensure_default_operation_tax()
            next_step = 'operations'
        elif self.current_step == 'operations':
            self._ensure_default_operation_fields()
            if self.operation_tax_enabled and not self.operation_tax_id:
                raise ValidationError(_('اختر الضريبة الافتراضية أو أوقف تطبيق الضريبة قبل المتابعة.'))
            self._sync_operation_compatibility()
            next_step = 'review'
        transition_vals = {'current_step': next_step}
        if self.state == 'draft':
            transition_vals['state'] = 'in_progress'
        self._write_setup_transition(transition_vals)
        self._audit_event('setup.step.advanced', {
            'from': previous_step,
            'to': self.current_step,
        })
        return self._setup_state_payload()

    def action_next(self):
        self.ensure_one()
        self.advance_setup()
        return self._wizard_action()

    def action_previous(self):
        self.ensure_one()
        self.retreat_setup()
        return self._wizard_action()

    def retreat_setup(self):
        """Return setup state data so web and future API callers share one path."""
        self.ensure_one()
        self._ensure_can_configure()
        previous = {'sizes': 'activity', 'services': 'sizes',
                    'operations': 'services', 'review': 'operations'}
        if self.current_step in previous:
            self._write_setup_transition({
                'current_step': previous[self.current_step],
            })
        return self._setup_state_payload()

    def activate_setup(self):
        self.ensure_one()
        self._ensure_can_configure()
        readiness = self.validate_readiness()
        if not readiness['ready']:
            raise ValidationError(_('لا يمكن تفعيل النظام الآن: %s') % self.readiness_note)
        self.apply_setup_templates()
        self._write_setup_transition({
            'state': 'ready', 'current_step': 'review',
            'completed_at': fields.Datetime.now(),
        })
        self._audit_event('setup.activated', {
            'version': self.setup_version,
            'service_count': len(self.service_line_ids.filtered('enabled')),
        })
        return self._setup_state_payload()

    def action_activate(self):
        self.ensure_one()
        self.activate_setup()
        return self.action_open_setup_center()

    def action_reopen_wizard(self):
        self.ensure_one()
        self.reopen_setup()
        return self._wizard_action()

    def reopen_setup(self):
        self.ensure_one()
        self._ensure_can_configure()
        self._write_setup_transition({
            'state': 'in_progress', 'current_step': 'activity',
        })
        self._audit_event('setup.reopened')
        return self._setup_state_payload()

    def apply_setup_templates(self):
        self.ensure_one()
        self._ensure_can_configure()
        readiness = self.validate_readiness()
        if not readiness['ready']:
            raise ValidationError(
                _('لا يمكن تطبيق القوالب الآن: %s') % self.readiness_note
            )
        company = self.company_id
        sizes = {}
        disabled_size_codes = self.size_line_ids.filtered(
            lambda line: not line.selected
        ).mapped('code')
        if disabled_size_codes:
            self.env['wof.car.size'].search([
                ('code', 'in', disabled_size_codes),
                ('company_id', '=', company.id),
            ]).write({'active': False})
        for draft in self.size_line_ids.filtered('selected'):
            record = self.env['wof.car.size'].search([
                ('code', '=', draft.code), ('company_id', '=', company.id),
            ], limit=1)
            vals = {
                'name': draft.name, 'code': draft.code,
                'company_id': company.id, 'active': True,
            }
            if record:
                record.write(vals)
            else:
                record = self.env['wof.car.size'].create(vals)
            sizes[draft.code] = record

        self._apply_tint_degrees()

        disabled_service_codes = self.service_line_ids.filtered(
            lambda line: not line.enabled
        ).mapped('code')
        if disabled_service_codes:
            disabled_services = self.env['wof.service.type'].search([
                ('code', 'in', disabled_service_codes),
                ('company_id', '=', company.id),
            ])
            disabled_services.write({'active': False})
            self.env['wof.film.category'].search([
                ('service_type_id', 'in', disabled_services.ids),
                ('company_id', '=', company.id),
            ]).write({'active': False})

        for draft in self.service_line_ids.filtered('enabled'):
            service = self.env['wof.service.type'].search([
                ('code', '=', draft.code),
                ('company_id', '=', company.id),
            ], limit=1)
            vals = {
                'name': draft.name, 'code': draft.code,
                'service_options': draft.service_kind,
                'company_id': company.id, 'active': True,
            }
            if service:
                service.write(vals)
            else:
                service = self.env['wof.service.type'].create(vals)

            film_code = '%s-DEFAULT' % draft.code
            film = self.env['wof.film.category'].search([
                ('code', '=', film_code), ('company_id', '=', company.id),
            ], limit=1)
            film_vals = {
                'name': draft.film_name, 'code': film_code,
                'service_type_id': service.id,
                'warranty_years': draft.warranty_years,
                'is_effected_in_inventory': draft.inventory_enabled and self.use_inventory,
                'active': True,
            }
            if film:
                film.write(film_vals)
            else:
                film = self.env['wof.film.category'].create(film_vals)

            grade_map = self._ensure_tint_grades(film)
            for part_template in draft.template_id.part_line_ids:
                part = self._ensure_part(part_template, draft)
                film_part = self.env['wof.film.parts.lines'].search([
                    ('header_id', '=', film.id), ('car_part_id', '=', part.id),
                ], limit=1)
                if not film_part:
                    film_part = self.env['wof.film.parts.lines'].create({
                        'header_id': film.id, 'car_part_id': part.id,
                    })
                if not film_part.film_category_line_id and grade_map:
                    default_grade = grade_map.get(
                        'CLR' if part_template.code == 'TINT-FRONT' else 'MED'
                    )
                    if default_grade:
                        film_part.write({
                            'film_category_line_id': default_grade.id,
                        })
                target_sizes = list(sizes.values()) if self.advanced_pricing else [False]
                for size in target_sizes:
                    self._ensure_price(film_part, size, draft, part_template)
                commission_sizes = list(sizes.values()) if self.advanced_commission else [False]
                for size in commission_sizes:
                    self._ensure_commission(film_part, size, draft)
        self._audit_event('setup.templates.applied', {
            'service_codes': self.service_line_ids.filtered('enabled').mapped('code'),
            'size_codes': self.size_line_ids.filtered('selected').mapped('code'),
        })

    def _ensure_tint_grades(self, service):
        """Create stable, reusable tint grades without duplicating setup data."""
        self.ensure_one()
        if not service.supports_color_grades:
            return {}
        grade_map = {}
        for sequence, code, name, transmission in (
            (10, 'CLR', 'شفاف', 70),
            (20, 'LGT', 'خفيف', 50),
            (30, 'MED', 'متوسط', 35),
            (40, 'DRK', 'داكن', 20),
        ):
            grade = self.env['wof.film.category.lines'].with_context(
                active_test=False
            ).search([
                ('header_id', '=', service.id),
                ('code', '=', code),
            ], limit=1)
            values = {
                'header_id': service.id,
                'sequence': sequence,
                'code': code,
                'name': name,
                'transmission_percent': transmission,
                'active': True,
            }
            if grade:
                grade.write(values)
            else:
                grade = self.env['wof.film.category.lines'].create(values)
            grade_map[code] = grade
        return grade_map

    def _ensure_part(self, template, service_draft):
        self.ensure_one()
        company = self.company_id
        part = self.env['wof.car.parts'].search([
            ('code', '=', template.code), ('company_id', '=', company.id),
        ], limit=1)
        products = self.env['product.product'].search([
            ('default_code', '=', template.code),
            ('type', '=', 'service'),
            ('company_id', '=', company.id),
        ], limit=2)
        if len(products) > 1:
            raise ValidationError(_(
                'يوجد أكثر من صنف خدمي بالكود %s في الشركة. '
                'وحّد الأكواد قبل تطبيق التهيئة.'
            ) % template.code)
        product = products
        if not product:
            products = self.env['product.product'].search([
                ('default_code', '=', template.code),
                ('type', '=', 'service'),
                ('company_id', '=', False),
            ], limit=2)
            if len(products) > 1:
                raise ValidationError(_(
                    'يوجد أكثر من صنف خدمي مشترك بالكود %s. '
                    'وحّد الأكواد قبل تطبيق التهيئة.'
                ) % template.code)
            product = products
        if not product:
            product_template = self.env['product.template'].create({
                'name': template.name, 'default_code': template.code,
                'type': 'service', 'sale_ok': True, 'purchase_ok': False,
                'company_id': company.id,
                'list_price': service_draft.base_price * template.price_ratio,
                'taxes_id': [(6, 0, service_draft.tax_id.ids)],
            })
            product = product_template.product_variant_id
        vals = {
            'name': template.name, 'code': template.code,
            'company_id': company.id, 'product_id': product.id, 'active': True,
        }
        if part:
            part.write(vals)
        else:
            part = self.env['wof.car.parts'].create(vals)
        return part

    def _ensure_price(self, film_part, size, draft, template):
        domain = [('part_line_id', '=', film_part.id),
                  ('car_size_id', '=', size.id if size else False)]
        price = self.env['wof.film.parts.price.lines'].search(domain, limit=1)
        vals = {
            'part_line_id': film_part.id,
            'car_size_id': size.id if size else False,
            'part_price': draft.base_price * template.price_ratio,
            'tax_id': draft.tax_id.id if draft.tax_id else False,
        }
        price.write(vals) if price else self.env['wof.film.parts.price.lines'].create(vals)

    def _ensure_commission(self, film_part, size, draft):
        domain = [('part_line_id', '=', film_part.id),
                  ('car_size_id', '=', size.id if size else False)]
        line = self.env['wof.film.parts.commission.lines'].search(domain, limit=1)
        vals = {
            'part_line_id': film_part.id,
            'car_size_id': size.id if size else False,
            'commission': draft.default_commission,
        }
        line.write(vals) if line else self.env['wof.film.parts.commission.lines'].create(vals)

    def action_open_setup_center(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('مركز إعدادات العناية'),
            'res_model': 'wof.company.profile', 'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('yousentech_wo_v4.view_wof_setup_center_form').id,
            'target': 'current',
        }

    def _related_action(self, xmlid, domain=None):
        self.ensure_one()
        action = self.env.ref(xmlid).read()[0]
        if domain is not None:
            action['domain'] = domain
        return action

    def action_open_services(self):
        return self._related_action(
            'yousentech_wo_v4.action_service_types_wo_v4',
            [('company_id', '=', self.company_id.id)],
        )

    def action_open_films(self):
        return self._related_action(
            'yousentech_wo_v4.action_film_category_wo_v4',
            [('company_id', '=', self.company_id.id)],
        )

    def action_open_sizes(self):
        return self._related_action(
            'yousentech_wo_v4.action_car_size_wo_v4',
            [('company_id', '=', self.company_id.id)],
        )

    def action_open_prices(self):
        return self._related_action(
            'yousentech_wo_v4.action_film_parts_price_lines',
            [('company_id', '=', self.company_id.id)],
        )

    def action_open_commissions(self):
        return self._related_action(
            'yousentech_wo_v4.action_film_parts_commission_lines',
            [('company_id', '=', self.company_id.id)],
        )


class WofSetupActivityLine(models.Model):
    _name = 'wof.setup.activity.line'
    _description = 'نشاط المنشأة في مركز التهيئة'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    profile_id = fields.Many2one(
        'wof.company.profile', required=True, ondelete='cascade', index=True,
    )
    company_id = fields.Many2one(
        related='profile_id.company_id', store=True, index=True, readonly=True,
    )
    activity_type = fields.Selection(
        SETUP_ACTIVITY_TYPES, string='نوع النشاط الداخلي',
        required=True, default='general', readonly=True,
    )
    name = fields.Char(string='اسم النشاط', required=True)
    description = fields.Text(string='ملاحظات')
    selected = fields.Boolean(string='تفعيل النشاط', default=False)
    is_system_default = fields.Boolean(default=False, readonly=True, copy=False)

    _sql_constraints = [
        ('setup_activity_name_profile_unique', 'unique(profile_id, name)',
         'اسم النشاط مستخدم مسبقًا في مركز التهيئة.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            profile = self.env['wof.company.profile'].browse(vals.get('profile_id')).exists()
            if not profile:
                raise ValidationError(_('يجب ربط النشاط بملف تهيئة صحيح.'))
            profile._ensure_can_configure()
            vals['name'] = (vals.get('name') or '').strip()
            if not vals['name']:
                raise ValidationError(_('اسم النشاط مطلوب.'))
        records = super().create(vals_list)
        for profile in records.mapped('profile_id'):
            if not self.env.context.get('skip_activity_legacy_sync'):
                profile.with_context(skip_activity_legacy_sync=True)._sync_legacy_activity_flags()
        return records

    def write(self, vals):
        self.mapped('profile_id')._ensure_can_configure()
        if 'activity_type' in vals and any(
            record.activity_type != vals['activity_type'] for record in self
        ):
            raise ValidationError(_(
                'نوع النشاط الداخلي ثابت. يمكنك تغيير اسم النشاط فقط.'
            ))
        if 'profile_id' in vals and any(
            record.profile_id.id != vals['profile_id'] for record in self
        ):
            raise ValidationError(_('لا يمكن نقل النشاط إلى ملف تهيئة آخر.'))
        if 'name' in vals:
            vals['name'] = (vals['name'] or '').strip()
            if not vals['name']:
                raise ValidationError(_('اسم النشاط مطلوب.'))
        result = super().write(vals)
        if {'selected', 'activity_type'}.intersection(vals) and not self.env.context.get('skip_activity_legacy_sync'):
            for profile in self.mapped('profile_id'):
                profile.with_context(skip_activity_legacy_sync=True)._sync_legacy_activity_flags()
        return result

    def unlink(self):
        if self.filtered('is_system_default'):
            raise ValidationError(_(
                'لا يمكن حذف النشاطات الأساسية. يمكنك إلغاء تفعيلها.'
            ))
        profiles = self.mapped('profile_id')
        profiles._ensure_can_configure()
        result = super().unlink()
        if not self.env.context.get('skip_activity_legacy_sync'):
            for profile in profiles:
                profile.with_context(skip_activity_legacy_sync=True)._sync_legacy_activity_flags()
        return result

    def action_edit_name(self):
        self.ensure_one()
        self.profile_id._ensure_can_configure()
        dialog = self.env['wof.setup.activity.dialog'].create({
            'mode': 'edit',
            'profile_id': self.profile_id.id,
            'activity_line_id': self.id,
            'name': self.name,
            'description': self.description or False,
        })
        return dialog._dialog_action()


class WofSetupSizeLine(models.Model):
    _name = 'wof.setup.size.line'
    _description = 'حجم سيارة في مسودة التهيئة'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    profile_id = fields.Many2one(
        'wof.company.profile', required=True, ondelete='cascade', index=True,
    )
    company_id = fields.Many2one(related='profile_id.company_id', store=True, index=True)
    selected = fields.Boolean(string="مفعّل", default=True)
    code = fields.Char(string="الكود", required=True)
    name = fields.Char(string="اسم الحجم", required=True)
    is_system_default = fields.Boolean(string="حجم افتراضي", default=False, readonly=True)

    _sql_constraints = [
        ('setup_size_code_profile_unique', 'unique(profile_id, code)',
         'كود الحجم مكرر في التهيئة.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if isinstance(vals.get('code'), str):
                vals['code'] = vals['code'].strip().upper()
        return super().create(vals_list)

    def write(self, vals):
        if 'profile_id' in vals and any(
            record.profile_id.id != vals['profile_id'] for record in self
        ):
            raise ValidationError(
                'لا يمكن نقل حجم التهيئة إلى ملف شركة آخر.'
            )
        if isinstance(vals.get('code'), str):
            normalized_code = vals['code'].strip().upper()
            if any(
                record.code != normalized_code and record.profile_id.completed_at
                for record in self
            ):
                raise ValidationError(
                    'لا يمكن تغيير كود حجم سبق تطبيقه. '
                    'ألغِ تفعيله وأضف حجمًا جديدًا بكود جديد.'
                )
            vals['code'] = normalized_code
        return super().write(vals)

    @api.constrains('code')
    def _check_technical_code(self):
        for record in self:
            if not TECHNICAL_CODE_RE.fullmatch(record.code or ''):
                raise ValidationError(
                    'كود الحجم يقبل الأحرف الإنجليزية الكبيرة والأرقام '
                    'والشرطة والنقطة والشرطة السفلية فقط.'
                )

    def action_edit_size(self):
        self.ensure_one()
        self.profile_id._ensure_can_configure()
        dialog = self.env['wof.setup.size.dialog'].create({
            'mode': 'edit',
            'profile_id': self.profile_id.id,
            'size_line_id': self.id,
            'name': self.name,
        })
        return dialog._dialog_action()


class WofSetupTintShadeLine(models.Model):
    _name = 'wof.setup.tint.shade.line'
    _description = 'درجة لون في مسودة التهيئة'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    profile_id = fields.Many2one(
        'wof.company.profile', required=True, ondelete='cascade', index=True,
    )
    company_id = fields.Many2one(
        related='profile_id.company_id', store=True, index=True, readonly=True,
    )
    numbering_method = fields.Selection(
        TINT_NUMBERING_METHODS, required=True, readonly=True,
    )
    value = fields.Char(string='درجة اللون', required=True, readonly=True)
    code = fields.Char(string='الكود', required=True, readonly=True)
    selected = fields.Boolean(string='مفعّل', default=True)

    _sql_constraints = [
        ('setup_tint_shade_profile_value_unique', 'unique(profile_id, value)',
         'درجة اللون مكررة في ملف التهيئة.'),
        ('setup_tint_shade_profile_code_unique', 'unique(profile_id, code)',
         'كود درجة اللون مكرر في ملف التهيئة.'),
    ]

    def write(self, vals):
        self.mapped('profile_id')._ensure_can_configure()
        immutable = {'profile_id', 'numbering_method', 'value', 'code'}
        if immutable.intersection(vals) and not self.env.context.get('wof_tint_setup_sync'):
            raise ValidationError(
                'قيم درجات اللون تُدار من طريقة الترقيم. يمكنك التفعيل أو الإلغاء فقط.'
            )
        return super().write(vals)

    def unlink(self):
        self.mapped('profile_id')._ensure_can_configure()
        return super().unlink()


class WofSetupOperationFieldLine(models.Model):
    _name = 'wof.setup.operation.field.line'
    _description = 'سياسة حقل أمر التركيب في التهيئة'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    profile_id = fields.Many2one(
        'wof.company.profile', required=True, ondelete='cascade', index=True,
    )
    company_id = fields.Many2one(
        related='profile_id.company_id', store=True, index=True, readonly=True,
    )
    field_key = fields.Selection(OPERATION_FIELD_KEYS, string='الحقل', required=True, readonly=True)
    label = fields.Char(string='الخاصية', required=True, readonly=True)
    required = fields.Boolean(string='إجباري')
    hidden = fields.Boolean(string='إخفاء')

    _sql_constraints = [
        ('setup_operation_field_profile_unique', 'unique(profile_id, field_key)',
         'الحقل موجود مسبقًا في إعدادات التشغيل.'),
    ]

    @api.onchange('hidden')
    def _onchange_hidden(self):
        for record in self:
            if record.hidden:
                record.required = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('hidden'):
                vals['required'] = False
        return super().create(vals_list)

    def write(self, vals):
        self.mapped('profile_id')._ensure_can_configure()
        immutable = {'profile_id', 'field_key', 'label'}
        if immutable.intersection(vals) and not self.env.context.get('wof_operation_setup_sync'):
            raise ValidationError(_('تعريف الحقول الرئيسية ثابت، ويمكن تعديل الإجباري والإخفاء فقط.'))
        if vals.get('hidden'):
            vals['required'] = False
        result = super().write(vals)
        return result

    @api.constrains('required', 'hidden')
    def _check_hidden_not_required(self):
        for record in self:
            if record.hidden and record.required:
                raise ValidationError(_('الحقل المخفي لا يمكن أن يكون إجباريًا.'))



class WofSetupServiceLine(models.Model):
    _name = 'wof.setup.service.line'
    _description = 'نشاط وخدمته الافتراضية في مسودة التهيئة'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    profile_id = fields.Many2one(
        'wof.company.profile', required=True, ondelete='cascade', index=True,
    )
    company_id = fields.Many2one(related='profile_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(
        related='company_id.currency_id', store=True, readonly=True,
    )
    template_id = fields.Many2one('wof.setup.template', ondelete='restrict')
    service_kind = fields.Selection(SERVICE_OPTIONS, required=True)
    enabled = fields.Boolean(string="مفعّلة", default=True)
    name = fields.Char(string="اسم نشاط المركز", required=True)
    code = fields.Char(string="الكود", required=True)
    film_name = fields.Char(string="اسم الخدمة / الفيلم الافتراضي", required=True)
    base_price = fields.Monetary(
        string="السعر الأساسي", currency_field='currency_id',
    )
    tax_id = fields.Many2one(
        'account.tax', string="الضريبة", check_company=True,
        domain="[('type_tax_use', '=', 'sale'), ('company_id', '=', company_id)]",
    )
    warranty_years = fields.Integer(string="سنوات الضمان", default=1)
    default_commission = fields.Monetary(
        string="عمولة الفني", currency_field='currency_id',
    )
    inventory_enabled = fields.Boolean(string="تستخدم المخزون")
    user_modified = fields.Boolean(default=False, copy=False)

    _sql_constraints = [
        ('setup_service_kind_profile_unique', 'unique(profile_id, service_kind)',
         'الخدمة مكررة في ملف التهيئة.'),
        ('setup_service_code_profile_unique', 'unique(profile_id, code)',
         'كود الخدمة مكرر في ملف التهيئة.'),
        ('setup_service_price_nonnegative', 'check(base_price >= 0)',
         'السعر لا يمكن أن يكون سالبًا.'),
        ('setup_service_commission_nonnegative', 'check(default_commission >= 0)',
         'العمولة لا يمكن أن تكون سالبة.'),
        ('setup_service_warranty_nonnegative', 'check(warranty_years >= 0)',
         'سنوات الضمان لا يمكن أن تكون سالبة.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if isinstance(vals.get('code'), str):
                vals['code'] = vals['code'].strip().upper()
        return super().create(vals_list)

    def write(self, vals):
        immutable = {'profile_id', 'template_id', 'service_kind', 'code'}
        if immutable.intersection(vals) and any(
            (
                record[field_name].id
                if record._fields[field_name].type == 'many2one'
                else record[field_name]
            ) != vals[field_name]
            for record in self
            for field_name in immutable.intersection(vals)
        ):
            raise ValidationError(
                'لا يمكن تغيير هوية خدمة التهيئة بعد إنشائها.'
            )
        if isinstance(vals.get('code'), str):
            vals['code'] = vals['code'].strip().upper()
        editable = {
            'name', 'code', 'film_name', 'base_price', 'tax_id',
            'warranty_years', 'default_commission', 'inventory_enabled',
        }
        if editable.intersection(vals) and not self.env.context.get('template_sync'):
            vals['user_modified'] = True
        return super().write(vals)

    @api.constrains('code')
    def _check_technical_code(self):
        for record in self:
            if not TECHNICAL_CODE_RE.fullmatch(record.code or ''):
                raise ValidationError(
                    'كود الخدمة يقبل الأحرف الإنجليزية الكبيرة والأرقام '
                    'والشرطة والنقطة والشرطة السفلية فقط.'
                )

    @api.constrains('template_id', 'service_kind', 'enabled')
    def _check_template_matches_service(self):
        for record in self.filtered('enabled'):
            if not record.template_id:
                raise ValidationError(
                    'الخدمة المفعّلة يجب أن ترتبط بقالب تهيئة.'
                )
            if record.template_id.service_kind != record.service_kind:
                raise ValidationError(
                    'قالب التهيئة لا يطابق نوع الخدمة.'
                )
