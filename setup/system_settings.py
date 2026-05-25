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
        'enable_work_order', 'plate_number_required', 'chassis_number_required',
        'customer_mobile_required', 'manufacture_year_required', 'car_color_required',
        'car_agency_required', 'delivery_datetime_required', 'allow_multiple_technicians',
        'technician_required', 'technician_commission_trigger', 'enable_discounts',
        'discount_level', 'allow_package_discount', 'propagate_discount_to_invoice',
        'enable_film_area_m2', 'enable_roll_consumption_tracking', 'roll_consumption_method',
        'removal_as_extra_service', 'create_invoice_after_full_payment',
        'auto_create_invoice_on_confirm', 'block_delivery_until_full_payment',
        'report_car_diagram_image', 'report_work_order_terms_image',
        'report_warranty_terms_image', 'report_invoice_terms_image',
        'enable_warranty_qr', 'report_footer_note', 'hide_plate_number',
        'hide_chassis_number', 'hide_manufacture_year', 'hide_car_color',
        'hide_odometer', 'hide_agency', 'hide_salesperson', 'hide_delivery_time',
        'hide_sticker_removal'
    )
    def _compute_ux_summary(self):
        for rec in self:
            work_fields = [
                rec.enable_work_order, rec.plate_number_required, rec.chassis_number_required,
                rec.customer_mobile_required, rec.manufacture_year_required, rec.car_color_required,
                rec.car_agency_required, rec.delivery_datetime_required, rec.allow_multiple_technicians,
                rec.technician_required,
            ]
            rec.work_order_total_count = len(work_fields)
            rec.work_order_enabled_count = sum(1 for value in work_fields if value)
            rec.work_order_completion = '%s/%s مفعلة' % (rec.work_order_enabled_count, rec.work_order_total_count)

            if rec.enable_discounts:
                rec.discount_summary = dict(rec._fields['discount_level'].selection).get(rec.discount_level, '')
            else:
                rec.discount_summary = 'الخصومات غير مفعلة'

            inventory_parts = []
            if rec.enable_roll_consumption_tracking:
                inventory_parts.append(dict(rec._fields['roll_consumption_method'].selection).get(rec.roll_consumption_method, ''))
            else:
                inventory_parts.append('تتبع الرول غير مفعل')
            if rec.enable_film_area_m2:
                inventory_parts.append('المتر المربع مفعل')
            rec.inventory_summary = ' - '.join([p for p in inventory_parts if p])

            report_enabled = sum(1 for value in [
                rec.report_car_diagram_image,
                rec.report_work_order_terms_image,
                rec.report_warranty_terms_image,
                rec.report_invoice_terms_image,
                rec.enable_warranty_qr,
                rec.report_footer_note,
            ] if value)
            rec.report_summary = '%s عناصر جاهزة' % report_enabled

            hidden_count = sum(1 for value in [
                rec.hide_plate_number, rec.hide_chassis_number, rec.hide_manufacture_year,
                rec.hide_car_color, rec.hide_odometer, rec.hide_agency,
                rec.hide_salesperson, rec.hide_delivery_time, rec.hide_sticker_removal,
            ] if value)
            rec.ui_summary = '%s حقول مخفية' % hidden_count

    @api.constrains('create_invoice_after_full_payment', 'auto_create_invoice_on_confirm')
    def _check_invoice_policy(self):
        for rec in self:
            if rec.create_invoice_after_full_payment and rec.auto_create_invoice_on_confirm:
                raise ValidationError(_('لا يمكن تفعيل سياستي إنشاء الفاتورة معاً. اختر بعد اكتمال الدفع أو عند التأكيد فقط.'))

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
        return super().create(vals_list)

    @api.model
    def get_company_settings(self, company=None):
        company = company or self.env.company
        company = company.parent_id or company
        settings = self.search([('company_id', '=', company.id)], limit=1)
        if not settings:
            settings = self.with_context(allow_wof_settings_create=True).create({'company_id': company.id})
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
