# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class WofSystemSettings(models.Model):
    _name = 'wof.system.settings'
    _description = 'إعدادات نظام أفلام السيارات'
    _rec_name = 'name'
    _order = 'company_id'

    name = fields.Char(string='الاسم', compute='_compute_name', store=True)
    company_id = fields.Many2one(
        'res.company',
        string='الشركة',
        required=True,
        default=lambda self: self._default_company_id(),
        index=True,
    )

    # Work Order settings
    enable_work_order = fields.Boolean(string='تفعيل أوامر التركيب', default=True)
    plate_number_required = fields.Boolean(string='رقم اللوحة إجباري', default=True)
    chassis_number_required = fields.Boolean(string='رقم الشاصي إجباري')
    customer_mobile_required = fields.Boolean(string='رقم جوال العميل إجباري', default=True)
    manufacture_year_required = fields.Boolean(string='سنة الصنع إجبارية')
    car_color_required = fields.Boolean(string='لون السيارة إجباري')
    car_agency_required = fields.Boolean(string='الوكالة إجبارية')
    delivery_datetime_required = fields.Boolean(string='تاريخ ووقت التسليم إجباري')
    allow_multiple_technicians = fields.Boolean(string='السماح بتعدد الفنيين', default=True)
    technician_required = fields.Boolean(string='الفني إجباري')
    technician_commission_trigger = fields.Selection(
        [
            ('invoice_posted', 'بعد ترحيل الفاتورة'),
            ('work_order_done', 'بعد إنجاز أمر التركيب'),
        ],
        string='اعتماد عمولة الفني',
        default='work_order_done',
        required=True,
    )

    # Discount settings
    enable_discounts = fields.Boolean(string='تفعيل الخصومات', default=True)
    discount_level = fields.Selection(
        [
            ('total', 'على مستوى الإجمالي'),
            ('service', 'على مستوى الخدمة'),
            ('service_detail', 'على مستوى تفاصيل الخدمة'),
        ],
        string='مستوى الخصم',
        default='total',
        required=True,
    )
    allow_package_discount = fields.Boolean(string='السماح بالخصم في الباقات')
    propagate_discount_to_invoice = fields.Boolean(string='ترحيل الخصم إلى الفاتورة')

    # Inventory and films
    enable_film_area_m2 = fields.Boolean(string='احتساب مقاس الفلم بالمتر المربع')
    enable_roll_consumption_tracking = fields.Boolean(string='تتبع استهلاك رول الفلم')
    roll_consumption_method = fields.Selection(
        [
            ('manual', 'يدوي'),
            ('car_parts', 'حسب أجزاء السيارة'),
            ('sizes', 'حسب المقاسات'),
        ],
        string='طريقة احتساب استهلاك الرول',
        default='manual',
        required=True,
    )
    removal_as_extra_service = fields.Boolean(string='إزالة الرواصق كخدمة إضافية', default=True)

    # Invoice and payment
    create_invoice_after_full_payment = fields.Boolean(string='إنشاء الفاتورة بعد اكتمال الدفع')
    auto_create_invoice_on_confirm = fields.Boolean(string='إنشاء فاتورة تلقائياً عند تأكيد أمر التركيب')
    block_delivery_until_full_payment = fields.Boolean(string='منع التسليم حتى سداد كامل المبلغ')

    # Reports
    report_car_diagram_image = fields.Binary(string='صورة مخطط السيارة', attachment=True)
    report_car_diagram_filename = fields.Char(string='اسم ملف مخطط السيارة')
    report_work_order_terms_image = fields.Binary(string='صورة شروط أمر التركيب', attachment=True)
    report_work_order_terms_filename = fields.Char(string='اسم ملف شروط أمر التركيب')
    report_warranty_terms_image = fields.Binary(string='صورة شروط الضمان', attachment=True)
    report_warranty_terms_filename = fields.Char(string='اسم ملف شروط الضمان')
    report_invoice_terms_image = fields.Binary(string='صورة شروط الفاتورة', attachment=True)
    report_invoice_terms_filename = fields.Char(string='اسم ملف شروط الفاتورة')
    report_footer_note = fields.Text(string='ملاحظة أسفل تقرير أمر التركيب')
    enable_warranty_qr = fields.Boolean(string='تفعيل QR الضمان', default=True)

    # Main screen UI
    hide_plate_number = fields.Boolean(string='إخفاء رقم اللوحة')
    hide_chassis_number = fields.Boolean(string='إخفاء رقم الشاصي')
    hide_manufacture_year = fields.Boolean(string='إخفاء سنة الصنع')
    hide_car_color = fields.Boolean(string='إخفاء لون السيارة')
    hide_odometer = fields.Boolean(string='إخفاء رقم العداد')
    hide_agency = fields.Boolean(string='إخفاء الوكالة')
    hide_salesperson = fields.Boolean(string='إخفاء المندوب')
    hide_delivery_time = fields.Boolean(string='إخفاء وقت التسليم')
    hide_sticker_removal = fields.Boolean(string='إخفاء إزالة الرواصق')
    hide_customer_mobile = fields.Boolean(string='إخفاء رقم جوال العميل')
    hide_technician = fields.Boolean(string='إخفاء الفني')
    odometer_required = fields.Boolean(string='رقم العداد إجباري')
    salesperson_required = fields.Boolean(string='المندوب إجباري')
    sticker_removal_required = fields.Boolean(string='إزالة الرواصق إجبارية')

    field_setting_line_ids = fields.One2many(
        'wof.system.field.setting',
        'settings_id',
        string='إعدادات الحقول الرئيسية',
        copy=False,
    )

    active = fields.Boolean(string='نشط', default=True)

    # UX summary fields
    work_order_enabled_count = fields.Integer(string='عدد إعدادات أوامر التركيب المفعلة', compute='_compute_ux_summary')
    work_order_total_count = fields.Integer(string='إجمالي إعدادات أوامر التركيب', compute='_compute_ux_summary')
    work_order_completion = fields.Char(string='اكتمال أوامر التركيب', compute='_compute_ux_summary')
    discount_summary = fields.Char(string='ملخص الخصومات', compute='_compute_ux_summary')
    inventory_summary = fields.Char(string='ملخص المخزون والأفلام', compute='_compute_ux_summary')
    report_summary = fields.Char(string='ملخص التقارير والضمان', compute='_compute_ux_summary')
    ui_summary = fields.Char(string='ملخص واجهة النظام', compute='_compute_ux_summary')

    _sql_constraints = [
        ('wof_system_settings_company_unique', 'unique(company_id)', 'يسمح بسجل إعدادات واحد فقط لكل شركة.'),
    ]

    @api.model
    def _default_company_id(self):
        company = self.env.company
        return company.parent_id.id or company.id

    @api.depends('company_id')
    def _compute_name(self):
        for rec in self:
            rec.name = _('إعدادات أفلام السيارات - %s') % (rec.company_id.display_name or '')

    @api.depends(
        'enable_work_order', 'allow_multiple_technicians', 'technician_commission_trigger',
        'enable_film_area_m2', 'removal_as_extra_service', 'auto_create_invoice_on_confirm',
        'report_car_diagram_image', 'report_work_order_terms_image',
        'report_warranty_terms_image', 'report_invoice_terms_image', 'report_footer_note',
        'field_setting_line_ids.required', 'field_setting_line_ids.hidden'
    )
    def _compute_ux_summary(self):
        for rec in self:
            enabled_count = sum(1 for value in [
                rec.enable_work_order,
                rec.allow_multiple_technicians,
                bool(rec.technician_commission_trigger),
            ] if value)
            rec.work_order_total_count = 3
            rec.work_order_enabled_count = enabled_count
            rec.work_order_completion = '%s/%s مفعلة' % (enabled_count, rec.work_order_total_count)

            # تبويب الخصومات أُلغي من الواجهة. نبقي الملخص متوافقاً مع الأكواد القديمة فقط.
            rec.discount_summary = 'ملغي من الإعدادات'

            inventory_parts = []
            if rec.enable_film_area_m2:
                inventory_parts.append('المتر المربع مفعل')
            else:
                inventory_parts.append('المتر المربع غير مفعل')
            if rec.removal_as_extra_service:
                inventory_parts.append('إزالة الرواصق كخدمة')
            rec.inventory_summary = ' - '.join([p for p in inventory_parts if p])

            report_enabled = sum(1 for value in [
                rec.report_car_diagram_image,
                rec.report_work_order_terms_image,
                rec.report_warranty_terms_image,
                rec.report_invoice_terms_image,
                rec.report_footer_note,
            ] if value)
            rec.report_summary = '%s عناصر جاهزة' % report_enabled

            hidden_count = sum(1 for line in rec.field_setting_line_ids if line.hidden)
            required_count = sum(1 for line in rec.field_setting_line_ids if line.required and not line.hidden)
            rec.ui_summary = '%s مخفية / %s إجبارية' % (hidden_count, required_count)

    @api.constrains('create_invoice_after_full_payment', 'auto_create_invoice_on_confirm')
    def _check_invoice_policy(self):
        for rec in self:
            if rec.create_invoice_after_full_payment and rec.auto_create_invoice_on_confirm:
                raise ValidationError(_('لا يمكن تفعيل سياستي إنشاء الفاتورة معاً. اختر بعد اكتمال الدفع أو عند التأكيد فقط.'))

    _FIELD_SETTING_CONFIG = [
        ('plate_number', 'رقم اللوحة', 'plate_number_required', 'hide_plate_number', 10),
        ('chassis_number', 'رقم الشاصي', 'chassis_number_required', 'hide_chassis_number', 20),
        ('customer_mobile', 'رقم جوال العميل', 'customer_mobile_required', 'hide_customer_mobile', 30),
        ('manufacture_year', 'سنة الصنع', 'manufacture_year_required', 'hide_manufacture_year', 40),
        ('car_color', 'لون السيارة', 'car_color_required', 'hide_car_color', 50),
        ('car_agency', 'الوكالة', 'car_agency_required', 'hide_agency', 60),
        ('delivery_datetime', 'تاريخ ووقت التسليم', 'delivery_datetime_required', 'hide_delivery_time', 70),
        ('odometer', 'رقم العداد', 'odometer_required', 'hide_odometer', 80),
        ('salesperson', 'المندوب', 'salesperson_required', 'hide_salesperson', 90),
        ('technician', 'الفني', 'technician_required', 'hide_technician', 100),
        ('sticker_removal', 'إزالة الرواصق', 'sticker_removal_required', 'hide_sticker_removal', 110),
    ]

    def _ensure_field_setting_lines(self):
        FieldLine = self.env['wof.system.field.setting'].sudo()
        for rec in self:
            existing_by_key = {line.field_key: line for line in rec.field_setting_line_ids}
            for key, label, required_field, hidden_field, sequence in rec._FIELD_SETTING_CONFIG:
                required_value = bool(getattr(rec, required_field, False))
                hidden_value = bool(getattr(rec, hidden_field, False))
                if hidden_value:
                    required_value = False
                    if getattr(rec, required_field, False):
                        rec.with_context(skip_field_line_sync=True).sudo().write({required_field: False})
                line = existing_by_key.get(key)
                vals = {
                    'settings_id': rec.id,
                    'sequence': sequence,
                    'field_key': key,
                    'name': label,
                    'required_field_name': required_field,
                    'hidden_field_name': hidden_field,
                    'required': required_value,
                    'hidden': hidden_value,
                }
                if line:
                    line.with_context(skip_parent_sync=True).write(vals)
                else:
                    FieldLine.with_context(skip_parent_sync=True).create(vals)
        return True

    def _sync_lines_from_boolean_fields(self, vals=None):
        for rec in self:
            rec._ensure_field_setting_lines()
            for line in rec.field_setting_line_ids:
                req = bool(getattr(rec, line.required_field_name, False)) if line.required_field_name else False
                hidden = bool(getattr(rec, line.hidden_field_name, False)) if line.hidden_field_name else False
                if hidden:
                    req = False
                line.with_context(skip_parent_sync=True).write({'required': req, 'hidden': hidden})

    @api.model_create_multi
    def create(self, vals_list):
        # إعدادات النظام لا تُنشأ يدوياً من زر جديد.
        # الإنشاء مسموح فقط من المعالج أو من الدالة المركزية التي تفتح إعدادات الشركة الأم.
        if not self.env.context.get('allow_wof_settings_create'):
            raise UserError(_('غير مسموح بإنشاء إعدادات جديدة يدوياً. افتح إعدادات النظام وسيتم استخدام سجل الشركة الأم تلقائياً.'))
        for vals in vals_list:
            company_id = vals.get('company_id') or self._default_company_id()
            company = self.env['res.company'].browse(company_id)
            parent_company = company.parent_id or company
            vals['company_id'] = parent_company.id
        records = super().create(vals_list)
        records._ensure_field_setting_lines()
        return records

    def write(self, vals):
        result = super().write(vals)
        if not self.env.context.get('skip_field_line_sync'):
            self._sync_lines_from_boolean_fields(vals)
        return result

    @api.model
    def get_company_settings(self, company=None):
        company = company or self.env.company
        company = company.parent_id or company
        settings = self.search([('company_id', '=', company.id)], limit=1)
        if not settings:
            settings = self.with_context(allow_wof_settings_create=True).create({'company_id': company.id})
        settings._ensure_field_setting_lines()
        return settings

    @api.model
    def action_open_current_company_settings(self):
        settings = self.get_company_settings()
        return {
            'type': 'ir.actions.act_window',
            'name': _('إعدادات أفلام السيارات'),
            'res_model': 'wof.system.settings',
            'view_mode': 'form',
            'res_id': settings.id,
            'target': 'current',
            'context': {
                'create': False,
                'delete': False,
                'default_company_id': settings.company_id.id,
            },
            'flags': {'mode': 'edit'},
        }

    def action_reset_default_master_data(self):
        self.ensure_one()
        self.env['wof.default.data.loader'].sudo().reset_default_master_data(self.company_id)

        # Open a fresh wizard after the reset. default_get will read the rebuilt
        # defaults and all selection checkboxes remain False.
        wizard = self.env['wof.setup.wizard'].sudo().create({'step': 'welcome'})
        return {
            'type': 'ir.actions.act_window',
            'name': _('معالج تهيئة نظام أفلام السيارات'),
            'res_model': 'wof.setup.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {'create': False, 'delete': False},
        }


class WofSystemFieldSetting(models.Model):
    _name = 'wof.system.field.setting'
    _description = 'إعدادات حقول نظام أفلام السيارات'
    _order = 'sequence, id'

    settings_id = fields.Many2one(
        'wof.system.settings',
        string='إعدادات النظام',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='الترتيب', default=10)
    field_key = fields.Char(string='الكود', required=True, readonly=True)
    name = fields.Char(string='الخاصية', required=True, readonly=True)
    required = fields.Boolean(string='إجباري')
    hidden = fields.Boolean(string='إخفاء')
    required_field_name = fields.Char(string='حقل الإجبار', readonly=True)
    hidden_field_name = fields.Char(string='حقل الإخفاء', readonly=True)

    _sql_constraints = [
        ('wof_system_field_setting_unique', 'unique(settings_id, field_key)', 'كل خاصية تظهر مرة واحدة فقط في إعدادات الشركة.'),
    ]

    @api.onchange('hidden')
    def _onchange_hidden(self):
        for line in self:
            if line.hidden:
                line.required = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('hidden'):
                vals['required'] = False
        records = super().create(vals_list)
        if not self.env.context.get('skip_parent_sync'):
            records._sync_to_parent_settings()
        return records

    def write(self, vals):
        if vals.get('hidden'):
            vals = dict(vals)
            vals['required'] = False
        result = super().write(vals)
        if not self.env.context.get('skip_parent_sync'):
            self._sync_to_parent_settings()
        return result

    def _sync_to_parent_settings(self):
        for line in self:
            updates = {}
            if line.required_field_name:
                updates[line.required_field_name] = bool(line.required and not line.hidden)
            if line.hidden_field_name:
                updates[line.hidden_field_name] = bool(line.hidden)
            if updates:
                line.settings_id.with_context(skip_field_line_sync=True).sudo().write(updates)
        return True
