# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


SERVICE_OPTIONS = [
    ('tint', 'عزل حراري'),
    ('ppf', 'حماية'),
    ('nano', 'نانو سيراميك'),
    ('upholstery', 'تنجيد'),
    ('floor_mats', 'أرضيات'),
    ('others', 'أخرى'),
]


class WofSetupWizard(models.TransientModel):
    _name = 'wof.setup.wizard'
    _description = 'WOF Setup Wizard'

    step = fields.Selection([('welcome', 'الترحيب'),
                            ('service_types', 'أنواع الخدمات'),
                            ('films', 'الأفلام'),
                                ], default='welcome')
    service_line_ids = fields.One2many(
        'wof.setup.wizard.service.line',
        'wizard_id',
        string="أنواع الخدمات"
    )
  
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        lines = []
        for option_key, option_label in SERVICE_OPTIONS:
            lines.append((0, 0, {
                'service_options': option_key,
                'custom_name': option_label,
            }))

        res['service_line_ids'] = lines
        return res

    def action_start_setup(self):
        self.ensure_one()
        self.step = 'service_types'
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wof.setup.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_back_welcome(self):
        self.ensure_one()
        self.step = 'welcome'
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wof.setup.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _get_service_code(self, option):
        return {
            'tint': 'TINT',
            'ppf': 'PPF',
            'nano': 'NANO',
            'upholstery': 'UPH',
            'floor_mats': 'MAT',
            'others': 'OTH',
        }.get(option, 'SRV')

    def action_create_service_types(self):
        self.ensure_one()

        selected_lines = self.service_line_ids.filtered('selected')
        if not selected_lines:
            raise ValidationError(_("يجب اختيار نوع خدمة واحد على الأقل."))

        company = self.env.company.parent_id or self.env.company
        ServiceType = self.env['wof.service.type'].sudo()

        for line in selected_lines:
            if not line.custom_name:
                raise ValidationError(_("يرجى إدخال اسم الخدمة المختارة."))

            service = ServiceType.search([
                ('service_options', '=', line.service_options),
                ('company_id', '=', company.id),
            ], limit=1)

            vals = {
                'name': line.custom_name,
                'code': self._get_service_code(line.service_options),
                'service_options': line.service_options,
                'company_id': company.id,
            }

            if service:
                service.write({
                    'name': line.custom_name,
                })
            else:
                ServiceType.create(vals)

        return True

    def action_finish_setup(self):
        self.action_create_service_types()

        self.env['ir.config_parameter'].sudo().set_param(
            'yousentech_wo_v4.setup_completed',
            True
        )

        return self.env.ref(
            'yousentech_wo_v4.action_service_types_wo_v4'
        ).read()[0]

    film_line_ids = fields.One2many('wof.setup.wizard.film.line','wizard_id',string="الأفلام")


    def action_go_films(self):
        self.ensure_one()

        # أولاً نحفظ أنواع الخدمات المختارة
        self.action_create_service_types()

        # تجهيز سطور الأفلام حسب الخدمات المختارة
        self.film_line_ids.unlink()

        company = self.env.company.parent_id or self.env.company

        service_types = self.env['wof.service.type'].search([
            ('company_id', '=', company.id),
            ('service_options', 'in', self.service_line_ids.filtered('selected').mapped('service_options')),
        ])

        lines = []
        for service in service_types:
            lines.append((0, 0, {
                'service_type_id': service.id,
                'film_name': service.name,
                'warranty_years': '5',
            }))

        self.write({
            'step': 'films',
            'film_line_ids': lines,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wof.setup.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }


    def action_back_service_types(self):
        self.ensure_one()
        self.step = 'service_types'

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wof.setup.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }


    def action_create_films(self):
        self.ensure_one()

        Film = self.env['wof.film.category'].sudo()
        company = self.env.company.parent_id or self.env.company

        for line in self.film_line_ids.filtered('selected'):

            if not line.film_name:
                raise ValidationError(_("يرجى إدخال اسم الفيلم."))

            if not line.service_type_id:
                raise ValidationError(_("يرجى تحديد نوع الخدمة للفيلم."))

            existing = Film.search([
                ('name', '=', line.film_name),
                ('service_type_id', '=', line.service_type_id.id),
                ('company_id', '=', company.id),
            ], limit=1)

            vals = {
                'name': line.film_name,
                'service_type_id': line.service_type_id.id,
                'warranty_years': line.warranty_years,
                'company_id': company.id,
            }

            if existing:
                existing.write(vals)
            else:
                Film.create(vals)

        return True


    def action_go_parts(self):
        self.ensure_one()

        self.action_create_films()

        # حالياً لا نفتح صفحة الأجزاء
        # فقط نحفظ الأفلام مبدئياً
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('تم الحفظ'),
                'message': _('تم حفظ الأفلام بنجاح. سنكمل صفحة الأجزاء في الخطوة التالية.'),
                'type': 'success',
                'sticky': False,
            }
        }


class WofSetupWizardServiceLine(models.TransientModel):
    _name = 'wof.setup.wizard.service.line'
    _description = 'WOF Setup Wizard Service Line'

    wizard_id = fields.Many2one(
        'wof.setup.wizard',
        string="المعالج",
        ondelete='cascade'
    )

    selected = fields.Boolean(
        string="اختيار"
    )

    service_options = fields.Selection(
        SERVICE_OPTIONS,
        string="النوع",
        required=False
    )

    custom_name = fields.Char(
        string="اسم الخدمة"
    )

    def action_open_line(self):

        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'تعديل الخدمة',
            'res_model': 'wof.setup.wizard.service.line',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class WofSetupWizardFilmLine(models.TransientModel):
    _name = 'wof.setup.wizard.film.line'
    _description = 'WOF Setup Wizard Film Line'

    wizard_id = fields.Many2one(
        'wof.setup.wizard',
        string="المعالج",
        ondelete='cascade'
    )

    selected = fields.Boolean(
        string="اختيار",
        default=True
    )

    service_type_id = fields.Many2one(
        'wof.service.type',
        string="نوع الخدمة",
        required=True
    )

    film_name = fields.Char(
        string="اسم الفيلم",
        required=True
    )

    warranty_years = fields.Char(
        string="سنوات الضمان"
    )