# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


SERVICE_OPTIONS = [
    ('tint', 'عزل حراري'),
]


CAR_SIZE_OPTIONS = [
    ('S', 'صغير'),
    ('M', 'متوسط'),
    ('L', 'كبير'),
    ('XL', 'كبير جداً'),
]


TINT_DEGREE_METHODS = [
    ('series', 'طريقة الأرقام 00-04'),
    ('percent', 'طريقة النسب شفاف - 35 -75'),
]

TINT_DEGREE_PRESETS = {
    'series': [
        ('الدرجة 1', 'شفاف'),
        ('الدرجة 2', '00'),
        ('الدرجة 3', '01'),
        ('الدرجة 4', '02'),
        ('الدرجة 5', '03'),
        ('الدرجة 6', '04'),
    ],
    'percent': [
         ('الدرجة 1', 'شفاف'),
        ('الدرجة 2', '00'),
        ('الدرجة 3', '35'),
        ('الدرجة 4', '50'),
        ('الدرجة 5', '70'),
        ('الدرجة 6', '75'),
    ],
}


class WofSetupWizard(models.Model):
    _name = 'wof.setup.wizard'
    _description = 'تهيئة نظام أفلام السيارات'
    _rec_name = 'display_name'
    _order = 'company_id, id'

    company_id = fields.Many2one(
        'res.company',
        string='الشركة الأم',
        required=True,
        default=lambda self: self._default_parent_company(),
        index=True,
        readonly=True,
    )
    display_name = fields.Char(string='الاسم', compute='_compute_display_name', store=True)

    _sql_constraints = [
        ('wof_setup_wizard_company_unique', 'unique(company_id)', 'يوجد سجل تهيئة واحد فقط لكل شركة أم.'),
    ]

    @api.model
    def _default_parent_company(self):
        company = self.env.company
        return company.parent_id.id or company.id

    @api.depends('company_id')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = _('تهيئة نظام أفلام السيارات - %s') % (rec.company_id.display_name or '')

    @api.model
    def get_company_setup(self):
        company = self.env.company
        parent = company.parent_id or company
        setup = self.sudo().search([('company_id', '=', parent.id)], limit=1)
        if not setup:
            setup = self.sudo().create({'company_id': parent.id, 'step': 'welcome'})
        if not setup.car_size_line_ids or not setup.tint_degree_line_ids or not setup.service_line_ids:
            setup._rebuild_lines_from_master_defaults()
        return setup

    @api.model
    def _open_company_setup_action(self, setup, name=None):
        return {
            'type': 'ir.actions.act_window',
            'name': name or _('تهيئة نظام أفلام السيارات'),
            'res_model': 'wof.setup.wizard',
            'res_id': setup.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {'create': False, 'delete': False},
            'flags': {'mode': 'edit'},
        }

    @api.model
    def action_open_company_setup(self):
        setup = self.get_company_setup()
        return self._open_company_setup_action(setup)

    @api.model
    def action_open_company_service_setup(self):
        """Open the singleton setup wizard directly on the services step.

        This is used after the initial setup is completed so managers can come
        back to the same wizard screen that contains the service cards instead
        of being sent to the normal CRUD kanban for service types.
        """
        setup = self.get_company_setup()
        if setup.step != 'service_types':
            setup.sudo().write({'step': 'service_types'})
        return self._open_company_setup_action(setup, _('تهيئة أنواع الخدمات'))

    def _rebuild_lines_from_master_defaults(self):
        self.ensure_one()
        defaults = self.default_get(['car_size_line_ids', 'tint_degree_line_ids', 'service_line_ids'])
        vals = {}
        for fname in ['car_size_line_ids', 'tint_degree_line_ids', 'service_line_ids']:
            if defaults.get(fname):
                vals[fname] = [(5, 0, 0)] + defaults[fname]
        if vals:
            self.sudo().write(vals)
        return True

    step = fields.Selection([
        ('welcome', 'الترحيب'),
        ('car_sizes', 'أحجام السيارة'),
        ('tint_degrees', 'درجات اللون'),
        ('service_types', 'أنواع الخدمات'),
        ('system_settings', 'الإعدادات العامة'),
    ], default='welcome')

    car_size_line_ids = fields.One2many(
        'wof.setup.wizard.car.size.line',
        'wizard_id',
        string="أحجام السيارة"
    )

    tint_degree_method = fields.Selection(
        TINT_DEGREE_METHODS,
        string="طريقة درجات اللون",
        default='series',
        required=True
    )

    tint_degree_line_ids = fields.One2many(
        'wof.setup.wizard.tint.degree.line',
        'wizard_id',
        string="درجات اللون"
    )

    service_line_ids = fields.One2many(
        'wof.setup.wizard.service.line',
        'wizard_id',
        string="أنواع الخدمات"
    )
    setup_locked = fields.Boolean(
    string="تم اعتماد المقاسات والدرجات",
    default=False )


    # الإعدادات العامة التي ستُرحّل إلى wof.system.settings في آخر خطوة من المعالج
    setup_enable_work_order = fields.Boolean(string='تفعيل أوامر التركيب', default=True)
    setup_plate_number_required = fields.Boolean(string='رقم اللوحة إجباري', default=True)
    setup_chassis_number_required = fields.Boolean(string='رقم الشاصي إجباري')
    setup_customer_mobile_required = fields.Boolean(string='رقم جوال العميل إجباري', default=True)
    setup_manufacture_year_required = fields.Boolean(string='سنة الصنع إجبارية')
    setup_car_color_required = fields.Boolean(string='لون السيارة إجباري')
    setup_car_agency_required = fields.Boolean(string='الوكالة إجبارية')
    setup_delivery_datetime_required = fields.Boolean(string='تاريخ ووقت التسليم إجباري')
    setup_allow_multiple_technicians = fields.Boolean(string='السماح بتعدد الفنيين', default=True)
    setup_technician_required = fields.Boolean(string='الفني إجباري')
    setup_technician_commission_trigger = fields.Selection(
        [('invoice_posted', 'بعد ترحيل الفاتورة'), ('work_order_done', 'بعد إنجاز أمر التركيب')],
        string='اعتماد عمولة الفني', default='work_order_done', required=True,
    )

    setup_enable_discounts = fields.Boolean(string='تفعيل الخصومات', default=True)
    setup_discount_level = fields.Selection(
        [('total', 'على مستوى الإجمالي'), ('service', 'على مستوى الخدمة'), ('service_detail', 'على مستوى تفاصيل الخدمة')],
        string='مستوى الخصم', default='total', required=True,
    )
    setup_allow_package_discount = fields.Boolean(string='السماح بالخصم في الباقات')
    setup_propagate_discount_to_invoice = fields.Boolean(string='ترحيل الخصم إلى الفاتورة')

    setup_enable_film_area_m2 = fields.Boolean(string='احتساب مقاس الفلم بالمتر المربع')
    setup_enable_roll_consumption_tracking = fields.Boolean(string='تتبع استهلاك رول الفلم')
    setup_roll_consumption_method = fields.Selection(
        [('manual', 'يدوي'), ('car_parts', 'حسب أجزاء السيارة'), ('sizes', 'حسب المقاسات')],
        string='طريقة احتساب استهلاك الرول', default='manual', required=True,
    )
    setup_removal_as_extra_service = fields.Boolean(string='إزالة الرواصق كخدمة إضافية', default=True)

    setup_create_invoice_after_full_payment = fields.Boolean(string='إنشاء الفاتورة بعد اكتمال الدفع')
    setup_auto_create_invoice_on_confirm = fields.Boolean(string='إنشاء فاتورة تلقائياً عند تأكيد أمر التركيب')
    setup_block_delivery_until_full_payment = fields.Boolean(string='منع التسليم حتى سداد كامل المبلغ')

    setup_enable_warranty_qr = fields.Boolean(string='تفعيل QR الضمان', default=True)
    setup_report_footer_note = fields.Text(string='ملاحظة أسفل تقرير أمر التركيب')
    setup_report_car_diagram_image = fields.Binary(string='صورة مخطط السيارة', attachment=True)
    setup_report_car_diagram_filename = fields.Char(string='اسم ملف مخطط السيارة')
    setup_report_work_order_terms_image = fields.Binary(string='صورة شروط أمر التركيب', attachment=True)
    setup_report_work_order_terms_filename = fields.Char(string='اسم ملف شروط أمر التركيب')
    setup_report_warranty_terms_image = fields.Binary(string='صورة شروط الضمان', attachment=True)
    setup_report_warranty_terms_filename = fields.Char(string='اسم ملف شروط الضمان')
    setup_report_invoice_terms_image = fields.Binary(string='صورة شروط الفاتورة', attachment=True)
    setup_report_invoice_terms_filename = fields.Char(string='اسم ملف شروط الفاتورة')

    setup_hide_plate_number = fields.Boolean(string='إخفاء رقم اللوحة')
    setup_hide_chassis_number = fields.Boolean(string='إخفاء رقم الشاصي')
    setup_hide_manufacture_year = fields.Boolean(string='إخفاء سنة الصنع')
    setup_hide_car_color = fields.Boolean(string='إخفاء لون السيارة')
    setup_hide_odometer = fields.Boolean(string='إخفاء رقم العداد')
    setup_hide_agency = fields.Boolean(string='إخفاء الوكالة')
    setup_hide_salesperson = fields.Boolean(string='إخفاء المندوب')
    setup_hide_delivery_time = fields.Boolean(string='إخفاء وقت التسليم')
    setup_hide_sticker_removal = fields.Boolean(string='إخفاء إزالة الرواصق')

    @api.model
    def reset_setup_temp_data(self):
        self.env['wof.setup.temp.film.tint.degree.line'].sudo().search([]).unlink()
        self.env['wof.setup.temp.film.part.commission.line'].sudo().search([]).unlink()
        self.env['wof.setup.temp.film.part.price.line'].sudo().search([]).unlink()
        self.env['wof.setup.temp.film.part'].sudo().search([]).unlink()
        self.env['wof.setup.temp.film'].sudo().search([]).unlink()

        self.env['wof.setup.film.tint.degree.line'].sudo().search([]).unlink()
        self.env['wof.setup.film.part.commission.line'].sudo().search([]).unlink()
        self.env['wof.setup.film.part.price.line'].sudo().search([]).unlink()
        self.env['wof.setup.film.part.line'].sudo().search([]).unlink()
        self.env['wof.setup.film.wizard'].sudo().search([]).unlink()

        self.env['wof.setup.wizard.service.line'].sudo().search([]).unlink()
        self.env['wof.setup.wizard.tint.degree.line'].sudo().search([]).unlink()
        self.env['wof.setup.wizard.car.size.line'].sudo().search([]).unlink()

        self.sudo().search([]).unlink()

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        # لا نحمل البيانات الافتراضية تلقائياً هنا.
        # المعالج يعرض القوالب المقترحة فقط إذا كانت السجلات الافتراضية محذوفة بعد إعادة التهيئة.

        if 'car_size_line_ids' in fields_list:
            size_lines = []
            Size = self.env['wof.car.size'].sudo()
            domain = [('active', '=', True)]
            if 'is_default_setup' in Size._fields:
                domain.append(('is_default_setup', '=', True))
            sizes = Size.search(domain, order='sequence, name' if 'sequence' in Size._fields else 'name')

            # Fallback آمن لو كانت نسخة قديمة بدون بيانات افتراضية.
            if not sizes:
                for seq, item in enumerate(self.env['wof.default.data.loader']._car_size_defaults(), start=1):
                    size_lines.append((0, 0, {
                        'sequence': item.get('sequence') or seq,
                        'selected': False,
                        'code': item.get('code'),
                        'name': item.get('name'),
                    }))
            else:
                for seq, size in enumerate(sizes, start=1):
                    size_lines.append((0, 0, {
                        'sequence': getattr(size, 'sequence', seq) or seq,
                        'selected': False,
                        'code': getattr(size, 'code', False),
                        'name': size.name,
                    }))
            res['car_size_line_ids'] = size_lines

        if 'tint_degree_line_ids' in fields_list:
            company = self.env.company.parent_id or self.env.company
            Tint = self.env['wof.tint.degree'].sudo()
            domain = [('active', '=', True), ('company_id', '=', company.id)]
            if 'is_default_setup' in Tint._fields:
                domain.append(('is_default_setup', '=', True))
            degrees = Tint.search(domain, order='sequence, value')
            degree_lines = []

            if degrees:
                for index, degree in enumerate(degrees, start=1):
                    degree_lines.append((0, 0, {
                        'sequence': degree.sequence or index,
                        'selected': False,
                        'name': degree.name,
                        'value': degree.value,
                    }))
            else:
                method = res.get('tint_degree_method') or 'series'
                values = TINT_DEGREE_PRESETS.get(method, [])
                for index, item in enumerate(values, start=1):
                    label, value = item
                    degree_lines.append((0, 0, {
                        'sequence': index,
                        'selected': False,
                        'name': label,
                        'value': value,
                    }))

            res['tint_degree_line_ids'] = degree_lines

        if 'service_line_ids' in fields_list:
            service_lines = []
            ServiceType = self.env['wof.service.type'].sudo()
            company = self.env.company.parent_id or self.env.company
            domain = [('company_id', '=', company.id)]
            if 'active' in ServiceType._fields:
                domain.append(('active', '=', True))
            if 'is_default_setup' in ServiceType._fields:
                domain.append(('is_default_setup', '=', True))
            services = ServiceType.search(domain, order='sequence, name' if 'sequence' in ServiceType._fields else 'name')

            sequence = 1
            if services:
                for service in services:
                    service_lines.append((0, 0, {
                        'sequence': sequence,
                        'service_type_id': service.id,
                        'default_code': service.code if 'code' in service._fields else False,
                        'selected': False,
                        'completed': False,
                        'service_options': 'tint' if ('service_options' in service._fields and service.service_options == 'tint') else False,
                        'custom_name': service.display_name,
                    }))
                    sequence += 1
            else:
                # بعد إعادة التهيئة لا توجد سجلات افتراضية في الجداول.
                # نعرض قوالب مقترحة داخل المعالج فقط، ولا ننشئ السجلات الأصلية إلا عند اختيارها وتفعيلها.
                for item in self.env['wof.default.data.loader']._service_defaults():
                    service_lines.append((0, 0, {
                        'sequence': item.get('sequence') or sequence,
                        'default_code': item.get('code'),
                        'selected': False,
                        'completed': False,
                        'service_options': item.get('service_options') or False,
                        'custom_name': item.get('name'),
                    }))
                    sequence += 1
            res['service_line_ids'] = service_lines

        setup_field_map = self._get_setup_settings_field_map()
        if any(field in fields_list for field in setup_field_map):
            settings = self.env['wof.system.settings'].sudo().get_company_settings()
            for wizard_field, settings_field in setup_field_map.items():
                if wizard_field in fields_list and settings_field in settings._fields:
                    res[wizard_field] = settings[settings_field]

        return res

    def _reload_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('تهيئة النظام'),
            'res_model': 'wof.setup.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_start_setup(self):
        self.ensure_one()
        self.step = 'car_sizes'
        return self._reload_wizard()

    def action_back_welcome(self):
        self.ensure_one()
        self.step = 'welcome'
        return self._reload_wizard()

    def action_back_car_sizes(self):
        self.ensure_one()
        self.step = 'car_sizes'
        return self._reload_wizard()

    def action_go_tint_degrees(self):
        self.ensure_one()

        selected_sizes = self.car_size_line_ids.filtered('selected')
        if not selected_sizes:
            raise ValidationError(_("يجب اختيار حجم سيارة واحد على الأقل."))

        for line in selected_sizes:
            if not line.name:
                raise ValidationError(_("يرجى إدخال اسم لكل حجم سيارة مختار."))

        self.step = 'tint_degrees'
        return self._reload_wizard()

    def action_back_tint_degrees(self):
        self.ensure_one()
        self.step = 'tint_degrees'
        return self._reload_wizard()

    @api.onchange('tint_degree_method')
    def action_apply_tint_degree_method(self):
        self.ensure_one()
        if not self.setup_locked:
            values = TINT_DEGREE_PRESETS.get(self.tint_degree_method, [])
            commands = [(5, 0, 0)]

            for index, item in enumerate(values, start=1):
                label, value = item
                commands.append((0, 0, {
                    'sequence': index,
                    'selected': False,
                    'name': label,
                    'value': value,
                }))

            self.write({
                'tint_degree_line_ids': commands
            })

            return self._reload_wizard()

    def action_go_service_types(self):
        self.ensure_one()

        selected_degrees = self.tint_degree_line_ids.filtered('selected')
        if not selected_degrees:
            raise ValidationError(_("يجب اختيار درجة لون واحدة على الأقل."))

        for line in selected_degrees:
            if not line.name or not line.value:
                raise ValidationError(_("يرجى إدخال المسمى والقيمة لكل درجة لون مختارة."))

        self.setup_locked = True
        self.step = 'service_types'
        return self._reload_wizard()

    def action_save_car_sizes(self):
        self.ensure_one()

        selected_sizes = self.car_size_line_ids.filtered('selected')
        if not selected_sizes:
            raise ValidationError(_("يجب اختيار حجم سيارة واحد على الأقل."))

        CarSize = self.env['wof.car.size'].sudo()
        size_map = {}

        for line in selected_sizes.sorted('sequence'):
            if not line.name:
                raise ValidationError(_("يرجى إدخال اسم لكل حجم سيارة مختار."))

            existing = CarSize.search([
                ('name', '=', line.name),
            ], limit=1)

            vals = {
                'name': line.name,
                'active': True,
            }

            if 'sequence' in CarSize._fields:
                vals['sequence'] = line.sequence

            if 'code' in CarSize._fields:
                vals['code'] = line.code
            if 'is_default_setup' in CarSize._fields:
                vals['is_default_setup'] = True

            if existing:
                existing.write(vals)
                size = existing
            else:
                size = CarSize.create(vals)

            size_map[line.id] = size.id

        return size_map

    def action_save_tint_degrees(self):
        self.ensure_one()

        selected_degrees = self.tint_degree_line_ids.filtered('selected')
        if not selected_degrees:
            return {}

        company = self.env.company.parent_id or self.env.company
        TintDegree = self.env['wof.tint.degree'].sudo()
        degree_map = {}

        for line in selected_degrees.sorted('sequence'):
            if not line.name or not line.value:
                raise ValidationError(_("يرجى إدخال المسمى والقيمة لكل درجة لون مختارة."))

            existing = TintDegree.search([
                ('value', '=', line.value),
                ('company_id', '=', company.id),
            ], limit=1)

            vals = {
                'sequence': line.sequence,
                'name': line.name,
                'value': line.value,
                'company_id': company.id,
                'active': True,
            }
            if 'is_default_setup' in TintDegree._fields:
                vals['is_default_setup'] = True

            if existing:
                existing.write(vals)
                degree = existing
            else:
                degree = TintDegree.create(vals)

            degree_map[line.id] = degree.id

        return degree_map

    def _get_service_code(self, option):
        return {
            'tint': 'TINT',
            'ppf': 'PPF',
            'nano': 'NANO',
            'upholstery': 'UPH',
            'floor_mats': 'MAT',
            'others': 'OTH',
        }.get(option, 'SRV')

    def _ensure_service_type_from_line(self, service_line):
        self.ensure_one()
        company = self.env.company.parent_id or self.env.company
        ServiceType = self.env['wof.service.type'].sudo()

        service = service_line.service_type_id.sudo() if service_line.service_type_id else ServiceType.browse()
        if not service:
            code = service_line.default_code or self._get_service_code(service_line.service_options)
            domain = [('company_id', '=', company.id)]
            if 'code' in ServiceType._fields and code:
                domain.append(('code', '=', code))
                service = ServiceType.search(domain, limit=1)
            if not service and service_line.custom_name:
                service = ServiceType.search([
                    ('company_id', '=', company.id),
                    ('name', '=', service_line.custom_name),
                ], limit=1)

            if not service:
                vals = {
                    'name': service_line.custom_name or _('خدمة جديدة'),
                    'company_id': company.id,
                }
                if 'sequence' in ServiceType._fields:
                    vals['sequence'] = service_line.sequence
                if 'code' in ServiceType._fields:
                    vals['code'] = code
                if 'service_options' in ServiceType._fields:
                    vals['service_options'] = service_line.service_options or False
                if 'setup_enabled' in ServiceType._fields:
                    vals['setup_enabled'] = True
                if 'is_default_setup' in ServiceType._fields:
                    vals['is_default_setup'] = True
                service = ServiceType.create(vals)
            service_line.service_type_id = service.id

        vals = {}
        if 'name' in ServiceType._fields and service_line.custom_name:
            vals['name'] = service_line.custom_name
        if 'code' in ServiceType._fields and service_line.default_code:
            vals['code'] = service_line.default_code
        if 'service_options' in ServiceType._fields:
            vals['service_options'] = service_line.service_options or False
        if 'setup_enabled' in ServiceType._fields:
            vals['setup_enabled'] = True
        if 'is_default_setup' in ServiceType._fields:
            vals['is_default_setup'] = True
        if vals:
            service.write(vals)

        self._ensure_default_parts_for_service(service)
        return service

    def _ensure_default_parts_for_service(self, service):
        self.ensure_one()
        company = self.env.company.parent_id or self.env.company
        Parts = self.env['wof.car.parts'].sudo()

        for item in self.env['wof.default.data.loader']._car_part_defaults():
            domain = [
                ('company_id', '=', company.id),
                ('service_type_id', '=', service.id),
                ('name', '=', item['name']),
            ]
            part = Parts.search(domain, limit=1)
            vals = {
                'name': item['name'],
                'company_id': company.id,
                'service_type_id': service.id,
                'active': True,
            }
            if 'priority_part' in Parts._fields:
                vals['priority_part'] = item.get('priority_part')
            if 'code' in Parts._fields:
                vals['code'] = item.get('code')
            if 'part_type' in Parts._fields:
                vals['part_type'] = item.get('part_type')
            if 'is_default_setup' in Parts._fields:
                vals['is_default_setup'] = True
            if part:
                part.write(vals)
            else:
                Parts.create(vals)
        return True

    def _get_size_key(self, line):
        return line.car_size_line_id.id if line.car_size_line_id else False

    def _get_part_size_ids(self, temp_part):
        size_ids = set()
        size_ids.update(temp_part.price_line_ids.mapped(lambda line: self._get_size_key(line)))
        size_ids.update(temp_part.commission_line_ids.mapped(lambda line: self._get_size_key(line)))
        return size_ids or {False}

    def _get_line_for_size(self, lines, size_id):
        return lines.filtered(lambda line: self._get_size_key(line) == size_id)[:1]

    def _create_or_update_film_parts(self, film, temp_part, size_map):
        FilmPartLine = self.env['wof.film.parts.lines'].sudo()
        PriceLine = self.env['wof.film.parts.price.lines'].sudo()
        CommissionLine = self.env['wof.film.parts.commission.lines'].sudo()

        part_line = FilmPartLine.search([
            ('header_id', '=', film.id),
            ('car_part_id', '=', temp_part.car_part_id.id),
        ], limit=1)

        part_vals = {
            'header_id': film.id,
            'car_part_id': temp_part.car_part_id.id,
            'part_selected': True,
        }

        if part_line:
            part_line.write(part_vals)
        else:
            part_line = FilmPartLine.create(part_vals)

        for price in temp_part.price_line_ids:
            real_size_id = size_map.get(price.car_size_line_id.id) if price.car_size_line_id else False

            vals = {
                'part_line_id': part_line.id,
                'car_size_id': real_size_id or False,
                'part_price': price.part_price,
                'discount_exceed_limit': price.discount_exceed_limit,
                'tax_id': price.tax_id.id if price.tax_id else False,
                'price_readonly': price.price_readonly,
                'free_part': price.free_part,
            }

            existing = PriceLine.search([
                ('part_line_id', '=', part_line.id),
                ('car_size_id', '=', real_size_id or False),
            ], limit=1)

            if existing:
                existing.write(vals)
            else:
                PriceLine.create(vals)

        for commission in temp_part.commission_line_ids:
            real_size_id = size_map.get(commission.car_size_line_id.id) if commission.car_size_line_id else False

            vals = {
                'part_line_id': part_line.id,
                'car_size_id': real_size_id or False,
                'commission': commission.commission,
            }

            existing = CommissionLine.search([
                ('part_line_id', '=', part_line.id),
                ('car_size_id', '=', real_size_id or False),
            ], limit=1)

            if existing:
                existing.write(vals)
            else:
                CommissionLine.create(vals)

    def _create_film_tint_degrees(self, film, temp_film, degree_map=None):
        self.ensure_one()

        service_options = False
        if film.service_type_id and 'service_options' in film.service_type_id._fields:
            service_options = film.service_type_id.service_options
        if service_options != 'tint':
            return

        FilmLine = self.env['wof.film.category.lines'].sudo()

        for degree in temp_film.tint_degree_line_ids.filtered('selected').sorted('sequence'):
            existing = FilmLine.search([
                ('header_id', '=', film.id),
                ('name', '=', degree.value),
            ], limit=1)

            vals = {
                'header_id': film.id,
                'name': degree.value,
            }

            if existing:
                existing.write(vals)
            else:
                FilmLine.create(vals)

    def _get_setup_settings_field_map(self):
        return {
            'setup_enable_work_order': 'enable_work_order',
            'setup_plate_number_required': 'plate_number_required',
            'setup_chassis_number_required': 'chassis_number_required',
            'setup_customer_mobile_required': 'customer_mobile_required',
            'setup_manufacture_year_required': 'manufacture_year_required',
            'setup_car_color_required': 'car_color_required',
            'setup_car_agency_required': 'car_agency_required',
            'setup_delivery_datetime_required': 'delivery_datetime_required',
            'setup_allow_multiple_technicians': 'allow_multiple_technicians',
            'setup_technician_required': 'technician_required',
            'setup_technician_commission_trigger': 'technician_commission_trigger',
            'setup_enable_discounts': 'enable_discounts',
            'setup_discount_level': 'discount_level',
            'setup_allow_package_discount': 'allow_package_discount',
            'setup_propagate_discount_to_invoice': 'propagate_discount_to_invoice',
            'setup_enable_film_area_m2': 'enable_film_area_m2',
            'setup_enable_roll_consumption_tracking': 'enable_roll_consumption_tracking',
            'setup_roll_consumption_method': 'roll_consumption_method',
            'setup_removal_as_extra_service': 'removal_as_extra_service',
            'setup_create_invoice_after_full_payment': 'create_invoice_after_full_payment',
            'setup_auto_create_invoice_on_confirm': 'auto_create_invoice_on_confirm',
            'setup_block_delivery_until_full_payment': 'block_delivery_until_full_payment',
            'setup_enable_warranty_qr': 'enable_warranty_qr',
            'setup_report_footer_note': 'report_footer_note',
            'setup_report_car_diagram_image': 'report_car_diagram_image',
            'setup_report_car_diagram_filename': 'report_car_diagram_filename',
            'setup_report_work_order_terms_image': 'report_work_order_terms_image',
            'setup_report_work_order_terms_filename': 'report_work_order_terms_filename',
            'setup_report_warranty_terms_image': 'report_warranty_terms_image',
            'setup_report_warranty_terms_filename': 'report_warranty_terms_filename',
            'setup_report_invoice_terms_image': 'report_invoice_terms_image',
            'setup_report_invoice_terms_filename': 'report_invoice_terms_filename',
            'setup_hide_plate_number': 'hide_plate_number',
            'setup_hide_chassis_number': 'hide_chassis_number',
            'setup_hide_manufacture_year': 'hide_manufacture_year',
            'setup_hide_car_color': 'hide_car_color',
            'setup_hide_odometer': 'hide_odometer',
            'setup_hide_agency': 'hide_agency',
            'setup_hide_salesperson': 'hide_salesperson',
            'setup_hide_delivery_time': 'hide_delivery_time',
            'setup_hide_sticker_removal': 'hide_sticker_removal',
        }

    def _validate_selected_services_ready(self):
        self.ensure_one()
        selected_services = self.service_line_ids.filtered('selected')
        if not selected_services:
            raise ValidationError(_("يجب اختيار نوع خدمة واحد على الأقل."))

        not_completed = selected_services.filtered(lambda line: not line.completed)
        if not_completed:
            names = ", ".join(not_completed.mapped('custom_name'))
            raise ValidationError(_("الخدمات التالية لم تكتمل تهيئتها:\n%s") % names)
        return selected_services

    def _apply_catalog_setup(self):
        self.ensure_one()

        size_map = self.action_save_car_sizes()
        degree_map = self.action_save_tint_degrees()
        selected_services = self._validate_selected_services_ready()

        company = self.env.company.parent_id or self.env.company
        FilmCategory = self.env['wof.film.category'].sudo()
        TempFilm = self.env['wof.setup.temp.film'].sudo()

        for service_line in selected_services:
            service = self._ensure_service_type_from_line(service_line)
            temp_films = TempFilm.search([
                ('wizard_id', '=', self.id),
                ('service_line_id', '=', service_line.id),
            ])

            for temp_film in temp_films:
                film = FilmCategory.search([
                    ('name', '=', temp_film.film_name),
                    ('service_type_id', '=', service.id),
                    ('company_id', '=', company.id),
                ], limit=1)

                film_vals = {
                    'name': temp_film.film_name,
                    'service_type_id': service.id,
                    'warranty_duration': temp_film.warranty_duration,
                    'warranty_period': temp_film.warranty_period,
                    'company_id': company.id,
                }

                if film:
                    film.write(film_vals)
                else:
                    film = FilmCategory.create(film_vals)

                self._create_film_tint_degrees(film, temp_film, degree_map)

                for temp_part in temp_film.part_line_ids:
                    if temp_part.car_part_id:
                        self._create_or_update_film_parts(film, temp_part, size_map)

    def action_go_system_settings(self):
        self.ensure_one()
        self._apply_catalog_setup()
        self.step = 'system_settings'
        return self._reload_wizard()

    def action_back_service_types(self):
        self.ensure_one()
        self.step = 'service_types'
        return self._reload_wizard()

    @api.constrains('setup_create_invoice_after_full_payment', 'setup_auto_create_invoice_on_confirm')
    def _check_setup_invoice_policy(self):
        for wizard in self:
            if wizard.setup_create_invoice_after_full_payment and wizard.setup_auto_create_invoice_on_confirm:
                raise ValidationError(_('لا يمكن تفعيل سياستي إنشاء الفاتورة معاً. اختر بعد اكتمال الدفع أو عند التأكيد فقط.'))

    def action_apply_general_settings(self):
        self.ensure_one()
        if self.setup_create_invoice_after_full_payment and self.setup_auto_create_invoice_on_confirm:
            raise ValidationError(_('لا يمكن تفعيل سياستي إنشاء الفاتورة معاً. اختر بعد اكتمال الدفع أو عند التأكيد فقط.'))

        settings = self.env['wof.system.settings'].sudo().get_company_settings()
        vals = {}
        for wizard_field, settings_field in self._get_setup_settings_field_map().items():
            if settings_field in settings._fields:
                vals[settings_field] = self[wizard_field]
        settings.write(vals)

        self.env['ir.config_parameter'].sudo().set_param('yousentech_wo_v4.setup_completed', True)

        return {
            'type': 'ir.actions.act_window',
            'name': _('إعدادات أفلام السيارات'),
            'res_model': 'wof.system.settings',
            'view_mode': 'form',
            'res_id': settings.id,
            'target': 'current',
        }

    def action_finish_all_setup(self):
        """توافق خلفي مع الزر القديم: يحفظ التهيئة وينقل المستخدم لخطوة الإعدادات العامة."""
        self.ensure_one()
        return self.action_go_system_settings()

    def action_unlock_base_setup(self):
        self.ensure_one()

        company = self.env.company.parent_id or self.env.company

        service_options = self.service_line_ids.filtered('selected').mapped('service_options')

        service_types = self.env['wof.service.type'].sudo().search([
            ('service_options', 'in', service_options),
            ('company_id', '=', company.id),
        ])

        films = self.env['wof.film.category'].sudo().search([
            ('service_type_id', 'in', service_types.ids),
            ('company_id', '=', company.id),
        ], limit=1)

        if films:
            raise ValidationError(_(
                "لا يمكن إعادة تهيئة المقاسات ودرجات اللون لأن هناك أفلام أو أجزاء تم إنشاؤها فعلياً وتعتمد على هذه الإعدادات.\n\n"
                "إذا أردت التعديل، قم بأرشفة أو حذف البيانات الأصلية المرتبطة أولاً."
            ))

        self.env['wof.setup.temp.film.tint.degree.line'].sudo().search([
            ('film_id.wizard_id', '=', self.id)
        ]).unlink()

        self.env['wof.setup.temp.film.part.commission.line'].sudo().search([
            ('temp_part_id.film_id.wizard_id', '=', self.id)
        ]).unlink()

        self.env['wof.setup.temp.film.part.price.line'].sudo().search([
            ('temp_part_id.film_id.wizard_id', '=', self.id)
        ]).unlink()

        self.env['wof.setup.temp.film.part'].sudo().search([
            ('film_id.wizard_id', '=', self.id)
        ]).unlink()

        self.env['wof.setup.temp.film'].sudo().search([
            ('wizard_id', '=', self.id)
        ]).unlink()

        self.env['wof.setup.film.tint.degree.line'].sudo().search([
            ('wizard_id.parent_wizard_id', '=', self.id)
        ]).unlink()

        self.env['wof.setup.film.part.commission.line'].sudo().search([
            ('part_line_id.wizard_id.parent_wizard_id', '=', self.id)
        ]).unlink()

        self.env['wof.setup.film.part.price.line'].sudo().search([
            ('part_line_id.wizard_id.parent_wizard_id', '=', self.id)
        ]).unlink()

        self.env['wof.setup.film.part.line'].sudo().search([
            ('wizard_id.parent_wizard_id', '=', self.id)
        ]).unlink()

        self.env['wof.setup.film.wizard'].sudo().search([
            ('parent_wizard_id', '=', self.id)
        ]).unlink()

        self.service_line_ids.write({
            'completed': False,
        })

        self.setup_locked = False
        self.step = 'car_sizes'

        return self._reload_wizard()
class WofSetupWizardCarSizeLine(models.Model):
    _name = 'wof.setup.wizard.car.size.line'
    _description = 'WOF Setup Wizard Car Size Line'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'wof.setup.wizard',
        string="المعالج",
        ondelete='cascade'
    )

    sequence = fields.Integer(string="الترتيب", default=10)
    selected = fields.Boolean(string="اختيار", default=False)
    code = fields.Char(string="الكود")
    name = fields.Char(string="اسم الحجم")

    def action_open_line(self):
        self.ensure_one()
        if self.wizard_id.setup_locked:
            raise ValidationError(_("لا يمكن تعديل حجم السيارة بعد اعتماد الإعدادات."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('تعديل حجم السيارة'),
            'res_model': 'wof.setup.wizard.car.size.line',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class WofSetupWizardTintDegreeLine(models.Model):
    _name = 'wof.setup.wizard.tint.degree.line'
    _description = 'WOF Setup Wizard Tint Degree Line'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'wof.setup.wizard',
        string="المعالج",
        ondelete='cascade'
    )

    sequence = fields.Integer(string="الترتيب", default=10)
    selected = fields.Boolean(string="اختيار", default=False)
    name = fields.Char(string="المسمى")
    value = fields.Char(string="القيمة")

    display_name = fields.Char(
        string="الاسم المعروض",
        compute="_compute_display_name"
    )

    @api.depends('name', 'value')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "%s - %s" % (rec.name or '', rec.value or '')

    def action_open_line(self):
        self.ensure_one()
        if self.wizard_id.setup_locked:
             raise ValidationError(_("لا يمكن تعديل درجة اللون بعد اعتماد الإعدادات."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('تعديل درجة اللون'),
            'res_model': 'wof.setup.wizard.tint.degree.line',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class WofSetupWizardServiceLine(models.Model):
    _name = 'wof.setup.wizard.service.line'
    _description = 'WOF Setup Wizard Service Line'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)

    wizard_id = fields.Many2one(
        'wof.setup.wizard',
        string="المعالج",
        ondelete='cascade'
    )

    service_type_id = fields.Many2one(
        'wof.service.type',
        string="نوع الخدمة",
        ondelete='cascade'
    )

    default_code = fields.Char(string="كود القالب")

    selected = fields.Boolean(string="اختيار")
    completed = fields.Boolean(string="مكتمل")

    service_options = fields.Selection(
        SERVICE_OPTIONS,
        string="محرك الخدمة",
        help="اتركه فارغاً للخدمات العادية. اختر عزل حراري فقط للخدمات التي تحتاج درجات لون ومناطق خدمة."
    )

    custom_name = fields.Char(string="اسم الخدمة")

    def action_open_line(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('تعديل الخدمة'),
            'res_model': 'wof.setup.wizard.service.line',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_open_service_setup(self):
        self.ensure_one()

        if not self.selected:
            raise ValidationError(_("يرجى تفعيل نوع الخدمة أولاً."))

        if not self.custom_name:
            self.custom_name = self.service_type_id.display_name if self.service_type_id else self.custom_name

        # بعد إعادة التهيئة قد تكون السجلات الأصلية محذوفة؛ ننشئ نوع الخدمة المختار وأجزاءه عند بدء تهيئته.
        service = self.wizard_id._ensure_service_type_from_line(self)

        if not self.custom_name:
            self.custom_name = service.display_name

        # المرحلة الأولى: تجهيز قالب أجزاء الخدمة فقط.
        # لا نطلب اسم الفيلم ولا الضمان هنا؛ المستخدم يختار الأجزاء المعتمدة أولاً.
        setup = self.env['wof.setup.film.wizard'].create({
            'parent_wizard_id': self.wizard_id.id,
            'service_line_id': self.id,
            'service_options': self.service_options or False,
            'service_name': self.custom_name,
            'film_step': 'template_parts',
            'parts_mode': 'parts',
        })

        # تحميل أجزاء السيارة كقالب أولي للخدمة.
        setup._load_service_parts_to_lines('car_part')

        return {
            'type': 'ir.actions.act_window',
            'name': _('تهيئة %s') % (self.custom_name or ''),
            'res_model': 'wof.setup.film.wizard',
            'res_id': setup.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_service_films(self):
        """Open a proper review board instead of a direct kanban.

        The board gives the user a summary header, a smart Add Film button,
        and the temporary film cards below it. This keeps the setup flow clear
        before finalizing the data into the real tables.
        """
        self.ensure_one()

        board = self.env['wof.setup.temp.film.board'].create({
            'wizard_id': self.wizard_id.id,
            'service_line_id': self.id,
        })
        board._load_films()

        view = self.env.ref(
            'yousentech_wo_v4.view_wof_setup_temp_film_board_form',
            raise_if_not_found=False
        )

        return {
            'type': 'ir.actions.act_window',
            'name': _('أفلام / أنواع %s') % (self.custom_name or self.service_type_id.display_name or ''),
            'res_model': 'wof.setup.temp.film.board',
            'res_id': board.id,
            'view_mode': 'form',
            'views': [(view.id, 'form')] if view else [(False, 'form')],
            'target': 'current',
        }


class WofSetupFilmWizard(models.Model):
    _name = 'wof.setup.film.wizard'
    _description = 'WOF Setup Film Wizard'

    parent_wizard_id = fields.Many2one(
        'wof.setup.wizard',
        string="معالج التهيئة",
        required=True,
        ondelete='cascade'
    )

    service_line_id = fields.Many2one(
        'wof.setup.wizard.service.line',
        string="نوع الخدمة المؤقت",
        required=True,
        ondelete='cascade'
    )

    service_options = fields.Selection(
        SERVICE_OPTIONS,
        string="محرك الخدمة"
    )

    service_type_id = fields.Many2one(
        'wof.service.type',
        string="نوع الخدمة",
        related='service_line_id.service_type_id',
        readonly=True,
        store=False,
    )

    temp_source_id = fields.Many2one(
        'wof.setup.temp.film',
        string="الفيلم المؤقت المصدر",
        readonly=True,
        ondelete='set null',
    )

    service_name = fields.Char(
        string="نوع الخدمة",
        required=True
    )

    film_name = fields.Char(
        string="اسم الفيلم"
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

    tint_degree_line_ids = fields.One2many(
        'wof.setup.film.tint.degree.line',
        'wizard_id',
        string="درجات اللون"
    )

    part_line_ids = fields.One2many(
        'wof.setup.film.part.line',
        'wizard_id',
        string="الأجزاء"
    )

    # واجهات عرض منفصلة لنفس السطور؛ تمنع خلط أجزاء السيارة مع مناطق الخدمة في نفس One2many.
    car_part_line_ids = fields.One2many(
        'wof.setup.film.part.line',
        'wizard_id',
        string="أجزاء السيارة",
        domain=[('line_role', '=', 'car_part')]
    )

    service_area_line_ids = fields.One2many(
        'wof.setup.film.part.line',
        'wizard_id',
        string="مناطق الخدمة",
        domain=[('line_role', '=', 'service_area')]
    )

    def _prepare_tint_degree_lines(self):
        self.ensure_one()

        if self.service_options != 'tint':
            return

        existing = self.tint_degree_line_ids.mapped('setup_degree_line_id')
        commands = []

        for degree in self.parent_wizard_id.tint_degree_line_ids.filtered('selected').sorted('sequence'):
            if degree not in existing:
                commands.append((0, 0, {
                    'sequence': degree.sequence,
                    'selected': True,
                    'setup_degree_line_id': degree.id,
                    'name': degree.name,
                    'value': degree.value,
                }))

        if commands:
            self.write({
                'tint_degree_line_ids': commands
            })

    def _save_current_film_to_temp(self):
        self.ensure_one()

        if not self.film_name:
            raise ValidationError(_("يرجى إدخال اسم الفيلم."))

        TempFilm = self.env['wof.setup.temp.film'].sudo()
        TempTint = self.env['wof.setup.temp.film.tint.degree.line'].sudo()
        TempPart = self.env['wof.setup.temp.film.part'].sudo()
        TempPrice = self.env['wof.setup.temp.film.part.price.line'].sudo()
        TempCommission = self.env['wof.setup.temp.film.part.commission.line'].sudo()

        existing_film = self.temp_source_id
        if not existing_film:
            existing_film = TempFilm.search([
                ('wizard_id', '=', self.parent_wizard_id.id),
                ('service_line_id', '=', self.service_line_id.id),
                ('film_name', '=', self.film_name),
            ], limit=1)

        if existing_film:
            existing_film.unlink()

        temp_film = TempFilm.create({
            'wizard_id': self.parent_wizard_id.id,
            'service_line_id': self.service_line_id.id,
            'film_name': self.film_name,
            'warranty_duration': self.warranty_duration,
            'warranty_period': self.warranty_period,
            'warranty_years': self.warranty_years,
        })

        if self.service_options == 'tint':
            for degree in self.tint_degree_line_ids.filtered('selected').sorted('sequence'):
                TempTint.create({
                    'film_id': temp_film.id,
                    'sequence': degree.sequence,
                    'selected': True,
                    'setup_degree_line_id': degree.setup_degree_line_id.id,
                    'name': degree.name,
                    'value': degree.value,
                })

        for part in self.part_line_ids.filtered('selected'):
            if not part.car_part_id:
                raise ValidationError(_("يرجى اختيار الجزء."))

            temp_part = TempPart.create({
                'film_id': temp_film.id,
                'car_part_id': part.car_part_id.id,
                'line_role': part.line_role or 'car_part',
            })

            for price in part.price_line_ids:
                TempPrice.create({
                    'temp_part_id': temp_part.id,
                    'car_size_line_id': price.car_size_line_id.id if price.car_size_line_id else False,
                    'part_price': price.part_price,
                    'discount_exceed_limit': price.discount_exceed_limit,
                    'tax_id': price.tax_id.id if price.tax_id else False,
                    'price_readonly': price.price_readonly,
                    'free_part': price.free_part,
                })

            for commission in part.commission_line_ids:
                TempCommission.create({
                    'temp_part_id': temp_part.id,
                    'car_size_line_id': commission.car_size_line_id.id if commission.car_size_line_id else False,
                    'commission': commission.commission,
                })

        return temp_film

    def action_add_new_film(self):
        self.ensure_one()
        return self.action_prepare_new_film()

    def action_complete_service_setup(self):
        self.ensure_one()

        if self.service_line_id.service_type_id:
            vals = {}
            if 'service_options' in self.service_line_id.service_type_id._fields:
                vals['service_options'] = self.service_options or False
            if 'setup_enabled' in self.service_line_id.service_type_id._fields:
                vals['setup_enabled'] = True
            if vals:
                self.service_line_id.service_type_id.sudo().write(vals)

        self.service_line_id.write({
            'completed': True,
            'selected': True,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('تهيئة النظام'),
            'res_model': 'wof.setup.wizard',
            'res_id': self.parent_wizard_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_back_to_services(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('تهيئة النظام'),
            'res_model': 'wof.setup.wizard',
            'res_id': self.parent_wizard_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_load_service_parts(self):
        # توافق خلفي فقط: تحميل أجزاء السيارة عند استدعاء الزر القديم.
        self.ensure_one()
        self._load_service_parts_to_lines('car_part')
        return self._reload_film_wizard()

    film_step = fields.Selection([
        ('template_parts', 'قالب الأجزاء'),
        ('info', 'بيانات النوع'),
        ('degrees', 'درجات اللون'),
        ('parts', 'التسعير والعمولات'),
        ('service_areas', 'مناطق الخدمة'),
    ], default='template_parts', string="مرحلة التهيئة")

    def _reload_film_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('تهيئة أنواع %s') % (self.service_name or ''),
            'res_model': 'wof.setup.film.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_start_new_film_from_template(self):
        self.ensure_one()

        selected_parts = self.car_part_line_ids.filtered('selected')
        if not selected_parts:
            raise ValidationError(_("يرجى اختيار جزء واحد على الأقل قبل إضافة نوع/فيلم."))

        self.write({
            'film_step': 'info',
            'parts_mode': 'parts',
            'film_name': False,
            'warranty_duration': 5,
            'warranty_period': 'year',
            'temp_source_id': False,
            'tint_degree_line_ids': [(5, 0, 0)],
        })

        if self.service_options == 'tint':
            self._prepare_tint_degree_lines()

        return self._reload_film_wizard()


    def action_film_next_degrees(self):
        self.ensure_one()

        if not self.film_name:
            raise ValidationError(_("يرجى إدخال اسم النوع."))

        if self.service_options == 'tint':
            self._prepare_tint_degree_lines()
            self.film_step = 'degrees'
            self.parts_mode = 'parts'
        else:
            # الخدمة العادية: بعد بيانات النوع ننتقل مباشرة إلى مرحلة إدخال الأسعار
            # على نفس الأجزاء التي تم اعتمادها في قالب الخدمة.
            self.film_step = 'parts'
            self.parts_mode = 'pricing'
            self._load_service_parts_to_lines('car_part')

        return self._reload_film_wizard()


    def action_film_back_info(self):
        self.ensure_one()
        self.film_step = 'info'
        return self._reload_film_wizard()
   
    def action_go_service_areas(self):
        self.ensure_one()

        if self.service_options != 'tint':
            return self.action_try_finish_current_film()

        self.film_step = 'service_areas'
        self.parts_mode = 'parts'
        self._load_service_parts_to_lines('service_area')

        return self._reload_film_wizard()

    def action_back_to_car_parts(self):
        self.ensure_one()

        self.film_step = 'parts'
        self.parts_mode = 'parts'
        self._load_service_parts_to_lines('car_part')

        return self._reload_film_wizard()

    def action_film_next_parts(self):
        self.ensure_one()

        # بعد بيانات النوع/درجات اللون ننتقل إلى شاشة الأجزاء في وضع الأسعار مباشرة،
        # مع استخدام نفس الأجزاء التي اعتمدها المستخدم في قالب الخدمة.
        self.film_step = 'parts'
        self.parts_mode = 'pricing'
        self._load_service_parts_to_lines('car_part')

        return self._reload_film_wizard()
  
    def _load_service_parts_to_lines(self, part_type='car_part'):
        self.ensure_one()

        if part_type not in ('car_part', 'service_area'):
            part_type = 'car_part'

        # حذف السطور الفارغة لنفس النوع فقط؛ لا نلمس النوع الآخر.
        empty_lines = self.part_line_ids.filtered(
            lambda line: line.line_role == part_type and not line.car_part_id
        )
        if empty_lines:
            empty_lines.unlink()

        Parts = self.env['wof.car.parts'].sudo()
        service_type = self.service_line_id.service_type_id
        if not service_type:
            raise ValidationError(_("نوع الخدمة غير محدد، لا يمكن جلب الأجزاء."))

        domain = [
            ('part_type', '=', part_type),
            ('active', '=', True),
            ('service_type_id', '=', service_type.id),
        ]

        parts = Parts.search(domain, order='priority_part, name')

        existing_parts = self.part_line_ids.filtered(
            lambda line: line.line_role == part_type
        ).mapped('car_part_id')

        commands = []
        for part in parts:
            if part not in existing_parts:
                commands.append((0, 0, {
                    'selected': False,
                    'car_part_id': part.id,
                    'line_role': part_type,
                }))

        if commands:
            self.write({'part_line_ids': commands})

        return True

    def action_film_back_degrees(self):
        self.ensure_one()

        if self.service_options == 'tint':
            self.film_step = 'degrees'
        else:
            self.film_step = 'info'

        return self._reload_film_wizard()

    def action_finish_current_film(self):
        self.ensure_one()

        if not self.film_name:
            raise ValidationError(_("يرجى إدخال اسم النوع."))

        if not self.part_line_ids.filtered('selected'):
            raise ValidationError(_("يرجى إضافة جزء واحد على الأقل قبل إنهاء تهيئة هذا النوع."))

        self._save_current_film_to_temp()

        wizard = self.env['wof.generic.done.wizard'].create({
            'title': _('تم حفظ النوع بنجاح'),
            'message': _(
                "تم حفظ بيانات النوع والأجزاء والتسعيرات والعمولات مؤقتاً.\n"
                "يمكنك الآن إضافة نوع آخر لنفس الخدمة أو إنهاء تهيئة هذه الخدمة."
            ),
            'primary_label': _('إضافة نوع آخر لنفس الخدمة'),
            'primary_action_key': 'add_new_film',
            'secondary_label': _('إنهاء تهيئة %s') % (self.service_name or _('الخدمة')),
            'secondary_action_key': 'complete_service_setup',
            'ref_model': self._name,
            'ref_id': self.id,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('تم الحفظ'),
            'res_model': 'wof.generic.done.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }


    def action_prepare_new_film(self):
        self.ensure_one()

        # عند إضافة نوع/فيلم آخر لنفس الخدمة نحتفظ بقالب الأجزاء المعتمد،
        # ونصفر فقط بيانات النوع والتسعيرات والعمولات والدرجات المختارة.
        self.part_line_ids.mapped('price_line_ids').unlink()
        self.part_line_ids.mapped('commission_line_ids').unlink()

        self.write({
            'film_name': False,
            'warranty_duration': 5,
            'warranty_period': 'year',
            'film_step': 'info',
            'parts_mode': 'parts',
            'temp_source_id': False,
            'tint_degree_line_ids': [(5, 0, 0)],
        })

        if self.service_options == 'tint':
            self._prepare_tint_degree_lines()

        return self._reload_film_wizard()


    def action_open_create_part_wizard(self):
        self.ensure_one()

        default_part_type = 'service_area' if self.film_step == 'service_areas' else 'car_part'

        return {
            'type': 'ir.actions.act_window',
            'name': _('إنشاء منطقة خدمة') if default_part_type == 'service_area' else _('إنشاء جزء جديد'),
            'res_model': 'wof.setup.create.part.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_setup_film_wizard_id': self.id,
                'default_service_type_id': self.service_line_id.service_type_id.id,
                'default_service_options': self.service_options,
                'default_part_type': default_part_type,
            }
        }


    parts_mode = fields.Selection([
    ('parts', 'الأجزاء'),
    ('pricing', 'إدخال الأسعار'),
    ('commission', 'عمولات الفنيين'), ], default='parts', string="وضع الأجزاء")


    def action_parts_mode_parts(self):
        self.ensure_one()
        self.parts_mode = 'parts'
        return self._reload_film_wizard()


    def action_parts_mode_pricing(self):
        self.ensure_one()
        self.parts_mode = 'pricing'
        return self._reload_film_wizard()


    def _get_current_part_role(self):
        self.ensure_one()
        return 'service_area' if self.film_step == 'service_areas' else 'car_part'

    def _get_current_selected_part_lines(self):
        self.ensure_one()
        role = self._get_current_part_role()
        return self.part_line_ids.filtered(
            lambda line: line.selected and line.line_role == role
        )

    def _get_parts_without_prices(self):
        self.ensure_one()

        missing_parts = self.env['wof.setup.film.part.line']

        for part in self._get_current_selected_part_lines():
            has_price = any(
                line.free_part or line.part_price > 0
                for line in part.price_line_ids
            )
            if not has_price:
                missing_parts |= part

        return missing_parts


    def action_parts_mode_commission(self):
        self.ensure_one()

        missing_parts = self._get_parts_without_prices()

        if missing_parts:
            wizard = self.env['wof.setup.parts.mode.confirm.wizard'].create({
                'setup_film_wizard_id': self.id,
                'message': _(
                    "توجد أجزاء لم يتم إدخال أسعار لها.\n\n"
                    "هل تريد الاستمرار إلى إدخال عمولات الفنيين؟"
                ),
            })

            return {
                'type': 'ir.actions.act_window',
                'name': _('تنبيه الأسعار'),
                'res_model': 'wof.setup.parts.mode.confirm.wizard',
                'res_id': wizard.id,
                'view_mode': 'form',
                'target': 'new',
            }

        self.parts_mode = 'commission'
        return self._reload_film_wizard()

    def _get_parts_without_commission(self):
        self.ensure_one()

        missing_parts = self.env['wof.setup.film.part.line']

        for part in self._get_current_selected_part_lines():
            if (
                part.line_role == 'service_area'
                and part.service_area_commission_method == 'from_part'
            ):
                continue

            has_commission = any(
                line.commission > 0
                for line in part.commission_line_ids
            )
            if not has_commission:
                missing_parts |= part

        return missing_parts


    def action_parts_back_to_pricing(self):
        self.ensure_one()
        self.parts_mode = 'pricing'
        return self._reload_film_wizard()


    def action_try_finish_current_film(self):
        self.ensure_one()

        missing_parts = self._get_parts_without_commission()

        if missing_parts:
            wizard = self.env['wof.setup.parts.commission.confirm.wizard'].create({
                'setup_film_wizard_id': self.id,
                'message': _(
                    "توجد أجزاء لم يتم إدخال عمولات لها.\n\n"
                    "هل تريد إنهاء تهيئة هذا النوع على كل حال؟"
                ),
            })

            return {
                'type': 'ir.actions.act_window',
                'name': _('تنبيه العمولات'),
                'res_model': 'wof.setup.parts.commission.confirm.wizard',
                'res_id': wizard.id,
                'view_mode': 'form',
                'target': 'new',
            }

        return self.action_finish_current_film()

class WofSetupFilmTintDegreeLine(models.Model):
    _name = 'wof.setup.film.tint.degree.line'
    _description = 'WOF Setup Film Tint Degree Line'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'wof.setup.film.wizard',
        string="معالج الفيلم",
        ondelete='cascade'
    )

    sequence = fields.Integer(string="الترتيب", default=10)
    selected = fields.Boolean(string="اختيار", default=True)

    setup_degree_line_id = fields.Many2one(
        'wof.setup.wizard.tint.degree.line',
        string="درجة التهيئة",
        ondelete='cascade'
    )

    name = fields.Char(string="المسمى")
    value = fields.Char(string="القيمة")


class WofSetupFilmPartLine(models.Model):
    _name = 'wof.setup.film.part.line'
    _description = 'WOF Setup Film Part Line'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)

    wizard_id = fields.Many2one(
        'wof.setup.film.wizard',
        string="معالج الفيلم",
        ondelete='cascade'
    )

    selected = fields.Boolean(
        string="اختيار",
        default=True
    )

    car_part_id = fields.Many2one(
        'wof.car.parts',
        string="الجزء"
    )

    price_line_count = fields.Integer(
        string="عدد تسعيرات الجزء",
        compute='_compute_pricing_summary'
    )

    commission_line_count = fields.Integer(
        string="عدد تسعيرات العمولة",
        compute='_compute_pricing_summary'
    )

    price_summary = fields.Char(
        string="ملخص أسعار الجزء",
        compute='_compute_pricing_summary'
    )

    commission_summary = fields.Char(
        string="ملخص العمولات",
        compute='_compute_pricing_summary'
    )

    price_line_ids = fields.One2many(
        'wof.setup.film.part.price.line',
        'part_line_id',
        string="التسعير حسب الحجم"
    )

    commission_line_ids = fields.One2many(
        'wof.setup.film.part.commission.line',
        'part_line_id',
        string="العمولة حسب الحجم"
    )
    service_options = fields.Selection(
        related='wizard_id.service_options',
        store=False
    )

    service_type_id = fields.Many2one(
        'wof.service.type',
        related='wizard_id.service_type_id',
        readonly=True,
        store=False,
    )

    line_role = fields.Selection([
        ('car_part', 'جزء سيارة'),
        ('service_area', 'منطقة خدمة')], string="نوع السطر", default='car_part', required=True)


    def _format_size_name(self, line):
        return line.car_size_line_id.display_name if line.car_size_line_id else _('كل الأحجام')
  
  
    service_area_commission_method = fields.Selection(
        related='car_part_id.service_area_commission_method',
        readonly=False,
        string="طريقة احتساب عمولة الفنيين" )


    @api.depends(
        'price_line_ids.car_size_line_id',
        'price_line_ids.part_price',
        'commission_line_ids.car_size_line_id',
        'commission_line_ids.commission',
    )
    def _compute_pricing_summary(self):
        for part in self:
            part.price_line_count = len(part.price_line_ids)
            part.commission_line_count = len(part.commission_line_ids)

            price_items = [
                _('%(size)s: %(amount).2f') % {
                    'size': part._format_size_name(line),
                    'amount': line.part_price,
                }
                for line in part.price_line_ids[:3]
            ]

            commission_items = [
                _('%(size)s: %(amount).2f') % {
                    'size': part._format_size_name(line),
                    'amount': line.commission,
                }
                for line in part.commission_line_ids[:3]
            ]

            if len(part.price_line_ids) > 3:
                price_items.append(_('والمزيد...'))

            if len(part.commission_line_ids) > 3:
                commission_items.append(_('والمزيد...'))

            part.price_summary = ' | '.join(price_items) or _('لم يتم إدخال أسعار')
            part.commission_summary = ' | '.join(commission_items) or _('لم يتم إدخال عمولات')

    def _check_part_selected(self):
        if not self.car_part_id:
            raise ValidationError(_("يرجى اختيار الجزء قبل فتح التسعير."))

    def _get_selected_size_lines(self):
        self.ensure_one()

        wizard = self.wizard_id.parent_wizard_id
        if not wizard:
            return self.env['wof.setup.wizard.car.size.line']

        return wizard.car_size_line_ids.filtered('selected').sorted('sequence')

    def _ensure_price_lines(self):
        self.ensure_one()

        size_lines = self._get_selected_size_lines()
        existing_sizes = self.price_line_ids.mapped('car_size_line_id')

        commands = []
        for size_line in size_lines:
            if size_line not in existing_sizes:
                commands.append((0, 0, {
                    'car_size_line_id': size_line.id,
                    'part_price': 0.0,
                    'discount_exceed_limit': 0,
                    'price_readonly': False,
                    'free_part': False,
                }))

        if commands:
            self.write({'price_line_ids': commands})

    def _ensure_commission_lines(self):
        self.ensure_one()

        size_lines = self._get_selected_size_lines()
        existing_sizes = self.commission_line_ids.mapped('car_size_line_id')

        commands = []
        for size_line in size_lines:
            if size_line not in existing_sizes:
                commands.append((0, 0, {
                    'car_size_line_id': size_line.id,
                    'commission': 0.0,
                }))

        if commands:
            self.write({'commission_line_ids': commands})

    def action_open_price_popup(self):
        self.ensure_one()
        self._check_part_selected()
        self._ensure_price_lines()

        return {
            'type': 'ir.actions.act_window',
            'name': _('أسعار %s') % (self.car_part_id.display_name or ''),
            'res_model': 'wof.setup.film.part.line',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref(
                'yousentech_wo_v4.view_wof_setup_film_part_price_form'
            ).id,
            'target': 'new',
        }

    def action_open_commission_popup(self):
        self.ensure_one()
        self._check_part_selected()
        self._ensure_commission_lines()

        return {
            'type': 'ir.actions.act_window',
            'name': _('عمولة %s') % (self.car_part_id.display_name or ''),
            'res_model': 'wof.setup.film.part.line',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref(
                'yousentech_wo_v4.view_wof_setup_film_part_commission_form'
            ).id,
            'target': 'new',
        }


class WofSetupFilmPartPriceLine(models.Model):
    _name = 'wof.setup.film.part.price.line'
    _description = 'WOF Setup Film Part Price Line'
    _order = 'id'

    part_line_id = fields.Many2one(
        'wof.setup.film.part.line',
        string="سطر الجزء",
        ondelete='cascade'
    )

    parent_wizard_id = fields.Many2one(
        related='part_line_id.wizard_id.parent_wizard_id',
        store=False
    )

    car_size_line_id = fields.Many2one(
        'wof.setup.wizard.car.size.line',
        string="حجم السيارة",
        domain="[('wizard_id', '=', parent_wizard_id), ('selected', '=', True)]"
    )

    part_price = fields.Float(string="السعر")
    discount_exceed_limit = fields.Integer(string="حد الخصم")

    tax_id = fields.Many2one(
        'account.tax',
        string="الضريبة",
        domain=[('type_tax_use', '=', 'sale')]
    )

    price_readonly = fields.Boolean(string="السعر ثابت")
    free_part = fields.Boolean(string="مجاني")

    @api.onchange('free_part')
    def _onchange_free_part(self):
        if self.free_part:
            self.part_price = 0.0
            self.price_readonly = True
            self.tax_id = False
            self.discount_exceed_limit = 0

    @api.constrains('part_line_id', 'car_size_line_id')
    def _check_unique_price_size(self):
        for line in self:
            if not line.part_line_id:
                continue

            duplicates = line.part_line_id.price_line_ids.filtered(
                lambda item:
                    item != line
                    and item.car_size_line_id == line.car_size_line_id
            )

            if duplicates:
                raise ValidationError(_("لا يمكن تكرار نفس حجم السيارة في تسعير الجزء."))


class WofSetupFilmPartCommissionLine(models.Model):
    _name = 'wof.setup.film.part.commission.line'
    _description = 'WOF Setup Film Part Commission Line'
    _order = 'id'

    part_line_id = fields.Many2one(
        'wof.setup.film.part.line',
        string="سطر الجزء",
        ondelete='cascade'
    )

    parent_wizard_id = fields.Many2one(
        related='part_line_id.wizard_id.parent_wizard_id',
        store=False
    )

    car_size_line_id = fields.Many2one(
        'wof.setup.wizard.car.size.line',
        string="حجم السيارة",
        domain="[('wizard_id', '=', parent_wizard_id), ('selected', '=', True)]"
    )

    commission = fields.Float(string="العمولة")

    @api.constrains('part_line_id', 'car_size_line_id')
    def _check_unique_commission_size(self):
        for line in self:
            if not line.part_line_id:
                continue

            duplicates = line.part_line_id.commission_line_ids.filtered(
                lambda item:
                    item != line
                    and item.car_size_line_id == line.car_size_line_id
            )

            if duplicates:
                raise ValidationError(_("لا يمكن تكرار نفس حجم السيارة في تسعير العمولة."))


class WofSetupTempFilm(models.Model):
    _name = 'wof.setup.temp.film'
    _description = 'WOF Setup Temp Film'
    _order = 'id'

    wizard_id = fields.Many2one(
        'wof.setup.wizard',
        string="معالج التهيئة",
        ondelete='cascade'
    )

    service_line_id = fields.Many2one(
        'wof.setup.wizard.service.line',
        string="نوع الخدمة المؤقت",
        ondelete='cascade'
    )

    service_name = fields.Char(
        related='service_line_id.custom_name',
        string="نوع الخدمة"
    )

    service_type_id = fields.Many2one(
        'wof.service.type',
        string="نوع الخدمة الأساسي",
        related='service_line_id.service_type_id',
        readonly=True,
        store=False,
    )

    service_options = fields.Selection(
        SERVICE_OPTIONS,
        string="محرك الخدمة",
        related='service_line_id.service_options',
        readonly=True,
        store=False,
    )

    part_count = fields.Integer(
        string="عدد الأجزاء",
        compute="_compute_setup_counts"
    )

    service_area_count = fields.Integer(
        string="عدد مناطق الخدمة",
        compute="_compute_setup_counts"
    )

    tint_degree_count = fields.Integer(
        string="عدد درجات اللون",
        compute="_compute_setup_counts"
    )

    film_name = fields.Char(string="اسم الفيلم")
    warranty_duration = fields.Integer(string="مدة الضمان")
    warranty_period = fields.Selection([
        ('day', 'يوم'),
        ('month', 'شهر'),
        ('year', 'سنة'),
        ('lifetime', 'مدى الحياة'),
    ], string="نوع مدة الضمان")
    warranty_years = fields.Char(string="مدة الضمان نصياً")

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

    tint_degree_line_ids = fields.One2many(
        'wof.setup.temp.film.tint.degree.line',
        'film_id',
        string="درجات اللون"
    )

    part_line_ids = fields.One2many(
        'wof.setup.temp.film.part',
        'film_id',
        string="الأجزاء"
    )

    @api.depends('part_line_ids.line_role', 'tint_degree_line_ids')
    def _compute_setup_counts(self):
        for rec in self:
            rec.part_count = len(rec.part_line_ids.filtered(lambda line: line.line_role == 'car_part'))
            rec.service_area_count = len(rec.part_line_ids.filtered(lambda line: line.line_role == 'service_area'))
            rec.tint_degree_count = len(rec.tint_degree_line_ids)

    def action_edit_temp_film(self):
        self.ensure_one()

        if not self.wizard_id or not self.service_line_id:
            raise ValidationError(_("لا يمكن تعديل هذا الفيلم لأن بيانات التهيئة المؤقتة غير مكتملة."))

        setup = self.env['wof.setup.film.wizard'].create({
            'parent_wizard_id': self.wizard_id.id,
            'service_line_id': self.service_line_id.id,
            'service_options': self.service_options or False,
            'service_name': self.service_name or self.service_line_id.custom_name,
            'film_name': self.film_name,
            'warranty_duration': self.warranty_duration,
            'warranty_period': self.warranty_period or 'year',
            'temp_source_id': self.id,
            'film_step': 'info',
            'parts_mode': 'parts',
        })

        tint_commands = []
        for degree in self.tint_degree_line_ids.sorted('sequence'):
            tint_commands.append((0, 0, {
                'sequence': degree.sequence,
                'selected': degree.selected,
                'setup_degree_line_id': degree.setup_degree_line_id.id if degree.setup_degree_line_id else False,
                'name': degree.name,
                'value': degree.value,
            }))
        if tint_commands:
            setup.write({'tint_degree_line_ids': tint_commands})
        elif setup.service_options == 'tint':
            setup._prepare_tint_degree_lines()

        part_commands = []
        for temp_part in self.part_line_ids:
            price_commands = []
            for price in temp_part.price_line_ids:
                price_commands.append((0, 0, {
                    'car_size_line_id': price.car_size_line_id.id if price.car_size_line_id else False,
                    'part_price': price.part_price,
                    'discount_exceed_limit': price.discount_exceed_limit,
                    'tax_id': price.tax_id.id if price.tax_id else False,
                    'price_readonly': price.price_readonly,
                    'free_part': price.free_part,
                }))

            commission_commands = []
            for commission in temp_part.commission_line_ids:
                commission_commands.append((0, 0, {
                    'car_size_line_id': commission.car_size_line_id.id if commission.car_size_line_id else False,
                    'commission': commission.commission,
                }))

            part_commands.append((0, 0, {
                'selected': True,
                'car_part_id': temp_part.car_part_id.id if temp_part.car_part_id else False,
                'line_role': temp_part.line_role or 'car_part',
                'price_line_ids': price_commands,
                'commission_line_ids': commission_commands,
            }))

        if part_commands:
            setup.write({'part_line_ids': part_commands})
        else:
            setup._load_service_parts_to_lines('car_part')

        return {
            'type': 'ir.actions.act_window',
            'name': _('تعديل %s') % (self.film_name or _('الفيلم')),
            'res_model': 'wof.setup.film.wizard',
            'res_id': setup.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_add_new_film_from_list(self):
        self.ensure_one()

        setup = self.env['wof.setup.film.wizard'].create({
            'parent_wizard_id': self.wizard_id.id,
            'service_line_id': self.service_line_id.id,
            'service_options': self.service_options or False,
            'service_name': self.service_name or self.service_line_id.custom_name,
            'film_step': 'template_parts',
            'parts_mode': 'parts',
        })
        setup._load_service_parts_to_lines('car_part')

        return {
            'type': 'ir.actions.act_window',
            'name': _('إضافة نوع / فيلم جديد'),
            'res_model': 'wof.setup.film.wizard',
            'res_id': setup.id,
            'view_mode': 'form',
            'target': 'current',
        }


    @api.model
    def action_back_to_service_types_from_context(self):
        wizard_id = self.env.context.get('setup_wizard_id') or self.env.context.get('default_wizard_id')
        if not wizard_id and self:
            wizard_id = self[:1].wizard_id.id
        if not wizard_id:
            raise ValidationError(_("لا يمكن الرجوع لأن معالج التهيئة غير محدد."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('تهيئة أنواع الخدمات'),
            'res_model': 'wof.setup.wizard',
            'res_id': wizard_id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def action_add_new_film_from_context(self):
        wizard_id = self.env.context.get('setup_wizard_id') or self.env.context.get('default_wizard_id')
        service_line_id = self.env.context.get('setup_service_line_id') or self.env.context.get('default_service_line_id')

        if not wizard_id or not service_line_id:
            if self:
                rec = self[:1]
                wizard_id = wizard_id or rec.wizard_id.id
                service_line_id = service_line_id or rec.service_line_id.id

        if not wizard_id or not service_line_id:
            raise ValidationError(_("لا يمكن إضافة فيلم جديد لأن بيانات الخدمة غير مكتملة."))

        service_line = self.env['wof.setup.wizard.service.line'].browse(service_line_id)
        if not service_line.exists():
            raise ValidationError(_("نوع الخدمة المؤقت غير موجود."))

        setup = self.env['wof.setup.film.wizard'].create({
            'parent_wizard_id': wizard_id,
            'service_line_id': service_line.id,
            'service_options': service_line.service_options or False,
            'service_name': service_line.custom_name or service_line.service_type_id.display_name,
            'film_step': 'template_parts',
            'parts_mode': 'parts',
        })
        setup._load_service_parts_to_lines('car_part')

        return {
            'type': 'ir.actions.act_window',
            'name': _('إضافة نوع / فيلم جديد'),
            'res_model': 'wof.setup.film.wizard',
            'res_id': setup.id,
            'view_mode': 'form',
            'target': 'current',
        }


class WofSetupTempFilmBoard(models.Model):
    _name = 'wof.setup.temp.film.board'
    _description = 'Temporary Film Setup Board'

    wizard_id = fields.Many2one(
        'wof.setup.wizard',
        string="معالج التهيئة",
        required=True,
        ondelete='cascade'
    )

    service_line_id = fields.Many2one(
        'wof.setup.wizard.service.line',
        string="نوع الخدمة",
        required=True,
        ondelete='cascade'
    )

    service_type_id = fields.Many2one(
        related='service_line_id.service_type_id',
        string="نوع الخدمة الأساسي",
        readonly=True,
        store=False
    )

    service_name = fields.Char(
        related='service_line_id.custom_name',
        string="اسم الخدمة",
        readonly=True,
        store=False
    )

    service_options = fields.Selection(
        SERVICE_OPTIONS,
        related='service_line_id.service_options',
        string="محرك الخدمة",
        readonly=True,
        store=False
    )

    film_ids = fields.Many2many(
        'wof.setup.temp.film',
        'wof_setup_temp_film_board_rel',
        'board_id',
        'film_id',
        string="الأفلام المؤقتة",
        readonly=True
    )

    film_count = fields.Integer(
        string="عدد الأفلام",
        compute='_compute_summary'
    )
    part_count = fields.Integer(
        string="إجمالي الأجزاء",
        compute='_compute_summary'
    )
    service_area_count = fields.Integer(
        string="مناطق الخدمة",
        compute='_compute_summary'
    )
    tint_degree_count = fields.Integer(
        string="درجات اللون",
        compute='_compute_summary'
    )

    @api.depends(
        'film_ids',
        'film_ids.part_count',
        'film_ids.service_area_count',
        'film_ids.tint_degree_count'
    )
    def _compute_summary(self):
        for rec in self:
            rec.film_count = len(rec.film_ids)
            rec.part_count = sum(rec.film_ids.mapped('part_count'))
            rec.service_area_count = sum(rec.film_ids.mapped('service_area_count'))
            rec.tint_degree_count = sum(rec.film_ids.mapped('tint_degree_count'))

    def _load_films(self):
        self.ensure_one()
        films = self.env['wof.setup.temp.film'].sudo().search([
            ('wizard_id', '=', self.wizard_id.id),
            ('service_line_id', '=', self.service_line_id.id),
        ], order='id desc')
        self.film_ids = [(6, 0, films.ids)]
        return True

    def action_back_to_service_types(self):
        self.ensure_one()
        self.wizard_id.step = 'service_types'
        return {
            'type': 'ir.actions.act_window',
            'name': _('تهيئة النظام'),
            'res_model': 'wof.setup.wizard',
            'res_id': self.wizard_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_add_new_film(self):
        self.ensure_one()

        setup = self.env['wof.setup.film.wizard'].create({
            'parent_wizard_id': self.wizard_id.id,
            'service_line_id': self.service_line_id.id,
            'service_options': self.service_line_id.service_options or False,
            'service_name': self.service_line_id.custom_name or self.service_line_id.service_type_id.display_name,
            'film_step': 'info',
            'parts_mode': 'parts',
        })

        setup._load_service_parts_to_lines('car_part')
        if setup.service_options == 'tint':
            setup._prepare_tint_degree_lines()

        return setup._reload_film_wizard()


class WofSetupTempFilmTintDegreeLine(models.Model):
    _name = 'wof.setup.temp.film.tint.degree.line'
    _description = 'WOF Setup Temp Film Tint Degree Line'
    _order = 'sequence, id'

    film_id = fields.Many2one(
        'wof.setup.temp.film',
        string="الفيلم المؤقت",
        ondelete='cascade'
    )

    sequence = fields.Integer(string="الترتيب", default=10)
    selected = fields.Boolean(string="اختيار", default=True)

    setup_degree_line_id = fields.Many2one(
        'wof.setup.wizard.tint.degree.line',
        string="درجة التهيئة",
        ondelete='cascade'
    )

    name = fields.Char(string="المسمى")
    value = fields.Char(string="القيمة")


class WofSetupTempFilmPart(models.Model):
    _name = 'wof.setup.temp.film.part'
    _description = 'WOF Setup Temp Film Part'
    _order = 'id'

    film_id = fields.Many2one(
        'wof.setup.temp.film',
        string="الفيلم المؤقت",
        ondelete='cascade'
    )

    car_part_id = fields.Many2one(
        'wof.car.parts',
        string="الجزء"
    )

    price_line_ids = fields.One2many(
        'wof.setup.temp.film.part.price.line',
        'temp_part_id',
        string="التسعير"
    )

    commission_line_ids = fields.One2many(
        'wof.setup.temp.film.part.commission.line',
        'temp_part_id',
        string="العمولة"
    )
    line_role = fields.Selection([
        ('car_part', 'جزء سيارة'),
        ('service_area', 'منطقة خدمة'),
    ], string="نوع السطر", default='car_part')

class WofSetupTempFilmPartPriceLine(models.Model):
    _name = 'wof.setup.temp.film.part.price.line'
    _description = 'WOF Setup Temp Film Part Price Line'
    _order = 'id'

    temp_part_id = fields.Many2one(
        'wof.setup.temp.film.part',
        string="الجزء المؤقت",
        ondelete='cascade'
    )

    car_size_line_id = fields.Many2one(
        'wof.setup.wizard.car.size.line',
        string="حجم السيارة"
    )

    part_price = fields.Float(string="السعر")
    discount_exceed_limit = fields.Integer(string="حد الخصم")

    tax_id = fields.Many2one(
        'account.tax',
        string="الضريبة",
        domain=[('type_tax_use', '=', 'sale')]
    )

    price_readonly = fields.Boolean(string="السعر ثابت")
    free_part = fields.Boolean(string="مجاني")


class WofSetupTempFilmPartCommissionLine(models.Model):
    _name = 'wof.setup.temp.film.part.commission.line'
    _description = 'WOF Setup Temp Film Part Commission Line'
    _order = 'id'

    temp_part_id = fields.Many2one(
        'wof.setup.temp.film.part',
        string="الجزء المؤقت",
        ondelete='cascade'
    )

    car_size_line_id = fields.Many2one(
        'wof.setup.wizard.car.size.line',
        string="حجم السيارة"
    )

    commission = fields.Float(string="العمولة")


class WofGenericDoneWizard(models.TransientModel):
    _name = 'wof.generic.done.wizard'
    _description = 'Generic Done Wizard'

    title = fields.Char(
        string="العنوان",
        required=True,
        default="تمت العملية بنجاح"
    )

    message = fields.Text(
        string="الرسالة",
        default="اختر الخطوة التالية."
    )

    primary_label = fields.Char(
        string="زر أول",
        default="متابعة"
    )

    secondary_label = fields.Char(
        string="زر ثاني",
        default="إنهاء"
    )

    ref_model = fields.Char(
        string="الموديل المرجعي",
        required=True
    )

    ref_id = fields.Integer(
        string="السجل المرجعي",
        required=True
    )

    primary_action_key = fields.Selection([
        ('add_new_film', 'إضافة نوع آخر'),
        ('complete_service_setup', 'إنهاء تهيئة الخدمة'),
    ], string="إجراء الزر الأول")

    secondary_action_key = fields.Selection([
        ('add_new_film', 'إضافة نوع آخر'),
        ('complete_service_setup', 'إنهاء تهيئة الخدمة'),
    ], string="إجراء الزر الثاني")

    def _get_ref_record(self):
        self.ensure_one()

        if not self.ref_model or not self.ref_id:
            raise ValidationError(_("لا يوجد سجل مرجعي لتنفيذ العملية."))

        if self.ref_model not in self.env:
            raise ValidationError(_("الموديل المرجعي غير موجود."))

        record = self.env[self.ref_model].browse(self.ref_id).exists()

        if not record:
            raise ValidationError(_("السجل المرجعي غير موجود أو تم حذفه."))

        return record

    def _execute_action_key(self, action_key):
        record = self._get_ref_record()

        allowed_actions = {
            'add_new_film': 'action_prepare_new_film',
            'complete_service_setup': 'action_complete_service_setup',
        }

        method_name = allowed_actions.get(action_key)

        if not method_name:
            raise ValidationError(_("الإجراء غير معروف."))

        if not hasattr(record, method_name):
            raise ValidationError(_("الإجراء غير متاح على السجل المرجعي."))

        return getattr(record, method_name)()

    def action_primary(self):
        self.ensure_one()
        return self._execute_action_key(self.primary_action_key)

    def action_secondary(self):
        self.ensure_one()
        return self._execute_action_key(self.secondary_action_key)

class WofSetupCreatePartWizard(models.TransientModel):
    _name = 'wof.setup.create.part.wizard'
    _description = 'WOF Setup Create Part Wizard'

    setup_film_wizard_id = fields.Many2one(
        'wof.setup.film.wizard',
        string="معالج الفيلم",
        required=True,
        ondelete='cascade'
    )

    service_type_id = fields.Many2one(
        'wof.service.type',
        string="نوع الخدمة",
        required=True,
        readonly=True,
    )

    name = fields.Char(
        string="اسم الجزء",
        required=True
    )

    code = fields.Char(
        string="الكود"
    )

    priority_part = fields.Integer(
        string="ترتيب الأولوية",
        default=10
    )

    service_options = fields.Selection(
        SERVICE_OPTIONS,
        string="نوع الخدمة",
        required=False
    )

    part_type = fields.Selection([
        ('car_part', 'جزء سيارة'),
        ('service_area', 'منطقة خدمة'),
    ], string="نوع الجزء", default='car_part', required=True)

    service_area_commission_method = fields.Selection([
                ('equal_from_area', 'توزيع عمولة منطقة الخدمة بالتساوي'),
                ('from_part', 'احتساب العمولة من الجزء'),
            ], string="طريقة احتساب عمولة الفنيين", default='equal_from_area')

    notes = fields.Char(string="ملاحظات")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        setup_id = self.env.context.get('default_setup_film_wizard_id')
        if setup_id:
            setup = self.env['wof.setup.film.wizard'].browse(setup_id).exists()
            if setup:
                res['setup_film_wizard_id'] = setup.id
                res['service_type_id'] = setup.service_line_id.service_type_id.id
                res['service_options'] = setup.service_options

        res.setdefault('part_type', 'car_part')

        return res

    def action_create_part(self):
        self.ensure_one()

        setup = self.setup_film_wizard_id
        if not setup:
            raise ValidationError(_("لم يتم العثور على معالج التهيئة."))

        Parts = self.env['wof.car.parts'].sudo()

        existing = Parts.search([
            ('name', '=', self.name),
            ('service_type_id', '=', setup.service_line_id.service_type_id.id),
            ('part_type', '=', self.part_type or 'car_part'),
        ], limit=1)

        if existing:
            raise ValidationError(_("هذا الجزء موجود مسبقاً."))

        company = self.env.company.parent_id or self.env.company

        Product = self.env['product.product'].sudo()
        product = Product.search([
            ('name', '=', self.name),
            ('type', '!=', 'product'),
        ], limit=1)
        if not product:
            product_template = self.env['product.template'].sudo().create({
                'name': self.name,
                'type': 'service',
            })
            product = product_template.product_variant_id

        vals = {
            'name': self.name,
            'code': self.code,
            'priority_part': self.priority_part,
            'company_id': company.id,
            'product_id': product.id,
            'service_area_commission_method': self.service_area_commission_method if self.part_type == 'service_area' else False,
            'service_type_id': setup.service_line_id.service_type_id.id,
            'part_type': self.part_type or 'car_part',
            'notes': self.notes,
            'active': True,
        }

        part = Parts.create(vals)

        existing_parts = setup.part_line_ids.mapped('car_part_id')
        if part not in existing_parts:
            setup.write({
                        'part_line_ids': [(0, 0, {
                        'selected': True,
                        'car_part_id': part.id,
                        'line_role': self.part_type or 'car_part',
                    })] })

        return setup._reload_film_wizard()
    
class WofSetupPartsCommissionConfirmWizard(models.TransientModel):
    _name = 'wof.setup.parts.commission.confirm.wizard'
    _description = 'WOF Setup Parts Commission Confirm Wizard'

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

    def action_back_to_commission(self):
        self.ensure_one()
        setup = self.setup_film_wizard_id
        setup.parts_mode = 'commission'
        return setup._reload_film_wizard()

    def action_finish_anyway(self):
        self.ensure_one()
        return self.setup_film_wizard_id.action_finish_current_film()