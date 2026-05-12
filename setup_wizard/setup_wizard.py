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

    step = fields.Selection([
        ('welcome', 'الترحيب'),
        ('service_types', 'أنواع الخدمات'),
    ], default='welcome')

    service_line_ids = fields.One2many(
        'wof.setup.wizard.service.line',
        'wizard_id',
        string="أنواع الخدمات"
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        if 'service_line_ids' in fields_list:
            lines = []
            sequence = 1
            for option_key, option_label in SERVICE_OPTIONS:
                lines.append((0, 0, {
                    'sequence': sequence,
                    'service_options': option_key,
                    'custom_name': option_label,
                }))
                sequence += 1

            res['service_line_ids'] = lines

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
        self.step = 'service_types'
        return self._reload_wizard()

    def action_back_welcome(self):
        self.ensure_one()
        self.step = 'welcome'
        return self._reload_wizard()

    def action_finish_all_setup(self):
        self.ensure_one()

        selected = self.service_line_ids.filtered('selected')
        not_completed = selected.filtered(lambda line: not line.completed)

        if not selected:
            raise ValidationError(_("يجب اختيار نوع خدمة واحد على الأقل."))

        if not_completed:
            names = ", ".join(not_completed.mapped('custom_name'))
            raise ValidationError(_("لم تكتمل تهيئة الخدمات التالية: %s") % names)

        self.env['ir.config_parameter'].sudo().set_param(
            'yousentech_wo_v4.setup_completed',
            True
        )

        for xmlid in [
            'yousentech_wo_v4.action_service_types_wo_v4',
            'yousentech_wo_v4.action_wof_service_type',
        ]:
            action = self.env.ref(xmlid, raise_if_not_found=False)
            if action:
                return action.read()[0]

        return {'type': 'ir.actions.client', 'tag': 'reload'}


class WofSetupWizardServiceLine(models.TransientModel):
    _name = 'wof.setup.wizard.service.line'
    _description = 'WOF Setup Wizard Service Line'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)

    wizard_id = fields.Many2one(
        'wof.setup.wizard',
        string="المعالج",
        ondelete='cascade'
    )

    selected = fields.Boolean(string="اختيار")

    completed = fields.Boolean(string="مكتمل")

    service_options = fields.Selection(
        SERVICE_OPTIONS,
        string="النوع",
        required=False
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
            raise ValidationError(_("يرجى اختيار نوع الخدمة أولاً."))

        if not self.custom_name:
            raise ValidationError(_("يرجى إدخال اسم نوع الخدمة."))

        setup = self.env['wof.setup.film.wizard'].create({
            'parent_wizard_id': self.wizard_id.id,
            'service_line_id': self.id,
            'service_options': self.service_options,
            'service_name': self.custom_name,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('تهيئة الأفلام والأجزاء'),
            'res_model': 'wof.setup.film.wizard',
            'res_id': setup.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_service_films(self):
        self.ensure_one()

        company = self.env.company.parent_id or self.env.company

        service = self.env['wof.service.type'].sudo().search([
            ('service_options', '=', self.service_options),
            ('company_id', '=', company.id),
        ], limit=1)

        if not service:
            raise ValidationError(_("لم يتم إنشاء نوع الخدمة بعد."))

        return {
            'type': 'ir.actions.act_window',
            'name': _('أفلام %s') % service.name,
            'res_model': 'wof.film.category',
            'view_mode': 'kanban,tree,form',
            'domain': [('service_type_id', '=', service.id)],
            'context': {
                'default_service_type_id': service.id,
            },
            'target': 'current',
        }


class WofSetupFilmWizard(models.TransientModel):
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
        string="النوع"
    )

    service_name = fields.Char(
        string="نوع الخدمة",
        required=True
    )

    film_name = fields.Char(
        string="اسم الفيلم",
       
    )

    warranty_years = fields.Char(
        string="سنوات الضمان",
        default="5"
    )

    part_line_ids = fields.One2many(
        'wof.setup.film.part.line',
        'wizard_id',
        string="الأجزاء"
    )

    def _get_service_code(self, option):
        return {
            'tint': 'TINT',
            'ppf': 'PPF',
            'nano': 'NANO',
            'upholstery': 'UPH',
            'floor_mats': 'MAT',
            'others': 'OTH',
        }.get(option, 'SRV')

    def _ensure_service_type(self):
        self.ensure_one()

        company = self.env.company.parent_id or self.env.company
        ServiceType = self.env['wof.service.type'].sudo()

        service = ServiceType.search([
            ('service_options', '=', self.service_options),
            ('company_id', '=', company.id),
        ], limit=1)

        vals = {
            'name': self.service_name,
            'code': self._get_service_code(self.service_options),
            'service_options': self.service_options,
            'company_id': company.id,
        }

        if service:
            service.write({
                'name': self.service_name,
            })
        else:
            service = ServiceType.create(vals)

        return service

    def _save_current_film(self):
        self.ensure_one()

        if not self.film_name:
            raise ValidationError(_("يرجى إدخال اسم الفيلم."))

        service = self._ensure_service_type()
        company = self.env.company.parent_id or self.env.company

        Film = self.env['wof.film.category'].sudo()

        film = Film.search([
            ('name', '=', self.film_name),
            ('service_type_id', '=', service.id),
            ('company_id', '=', company.id),
        ], limit=1)

        film_vals = {
            'name': self.film_name,
            'service_type_id': service.id,
            'warranty_years': self.warranty_years,
            'company_id': company.id,
        }

        if film:
            film.write(film_vals)
        else:
            film = Film.create(film_vals)

        FilmPartLine = self.env['wof.film.parts.lines'].sudo()

        for part in self.part_line_ids.filtered('selected'):

            if not part.car_part_id:
                raise ValidationError(_("يرجى اختيار الجزء."))

            price_lines = part.price_line_ids
            commission_lines = part.commission_line_ids

            # لو المستخدم أضاف جزء بدون تسعير ولا عمولة
            if not price_lines and not commission_lines:

                domain = [
                    ('header_id', '=', film.id),
                    ('car_part_id', '=', part.car_part_id.id),
                    ('car_size_id', '=', False),
                ]

                vals = {
                    'header_id': film.id,
                    'car_part_id': part.car_part_id.id,
                    'car_size_id': False,
                    'part_price': 0.0,
                    'commission': 0.0,
                    'discount_exceed_limit': 0,
                    'tax_id': False,
                    'price_readonly': False,
                    'free_part': False,
                }

                existing = FilmPartLine.search(domain, limit=1)
                if existing:
                    existing.write(vals)
                else:
                    FilmPartLine.create(vals)

                continue

            # الأحجام الموجودة في التسعير أو العمولة
            size_keys = set()

            for price in price_lines:
                size_keys.add(price.car_size_id.id if price.car_size_id else False)

            for commission in commission_lines:
                size_keys.add(commission.car_size_id.id if commission.car_size_id else False)

            for size_id in size_keys:

                price_line = price_lines.filtered(
                    lambda l: (l.car_size_id.id if l.car_size_id else False) == size_id
                )[:1]

                commission_line = commission_lines.filtered(
                    lambda l: (l.car_size_id.id if l.car_size_id else False) == size_id
                )[:1]

                domain = [
                    ('header_id', '=', film.id),
                    ('car_part_id', '=', part.car_part_id.id),
                    ('car_size_id', '=', size_id or False),
                ]

                vals = {
                    'header_id': film.id,
                    'car_part_id': part.car_part_id.id,
                    'car_size_id': size_id or False,

                    'part_price': price_line.part_price if price_line else 0.0,

                    'commission': commission_line.commission if commission_line else 0.0,

                    'discount_exceed_limit': (
                        price_line.discount_exceed_limit if price_line else 0
                    ),

                    'tax_id': (
                        price_line.tax_id.id if price_line and price_line.tax_id else False
                    ),

                    'price_readonly': (
                        price_line.price_readonly if price_line else False
                    ),

                    'free_part': (
                        price_line.free_part if price_line else False
                    ),
                }

                existing = FilmPartLine.search(domain, limit=1)

                if existing:
                    existing.write(vals)
                else:
                    FilmPartLine.create(vals)

        return film
    def action_add_new_film(self):
        self.ensure_one()

        self._save_current_film()

        self.write({
            'film_name': False,
            'warranty_years': '5',
            'part_line_ids': [(5, 0, 0)],
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('تهيئة الأفلام والأجزاء'),
            'res_model': 'wof.setup.film.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_complete_service_setup(self):
        self.ensure_one()

        self._save_current_film()

        self.service_line_id.completed = True
        self.service_line_id.selected = True

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


class WofSetupFilmPartLine(models.TransientModel):
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
        string="الجزء",
        required=True
    )

    price_line_ids = fields.One2many(
        'wof.setup.film.part.price.line',
        'part_line_id',
        string="التسعير حسب الحجم" )

    commission_line_ids = fields.One2many(
        'wof.setup.film.part.commission.line',
        'part_line_id',
        string="العمولة حسب الحجم"  )

    def action_open_price_popup(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('تسعير الجزء حسب حجم السيارة'),
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
        return {
            'type': 'ir.actions.act_window',
            'name': _('عمولة الفني حسب حجم السيارة'),
            'res_model': 'wof.setup.film.part.line',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref(
                'yousentech_wo_v4.view_wof_setup_film_part_commission_form'
            ).id,
            'target': 'new',
        }


class WofSetupFilmPartSizeLine(models.TransientModel):
    _name = 'wof.setup.film.part.size.line'
    _description = 'WOF Setup Film Part Size Line'
    _order = 'id'

    part_line_id = fields.Many2one(
        'wof.setup.film.part.line',
        string="سطر الجزء",
        ondelete='cascade'
    )

    car_size_id = fields.Many2one(
        'wof.car.size',
        string="حجم السيارة"
    )

    part_price = fields.Float(
        string="سعر الجزء"
    )

    commission = fields.Float(
        string="عمولة الفني"
    )

    discount_exceed_limit = fields.Integer(
        string="نسبة الخصم المسموح"
    )

    tax_id = fields.Many2one(
        'account.tax',
        string="الضريبة",
        domain=[('type_tax_use', '=', 'sale')]
    )

    price_readonly = fields.Boolean(
        string="السعر ثابت"
    )

    free_part = fields.Boolean(
        string="جزء مجاني"
    )


class WofSetupFilmPartPriceLine(models.TransientModel):
    _name = 'wof.setup.film.part.price.line'
    _description = 'WOF Setup Film Part Price Line'

    part_line_id = fields.Many2one(
        'wof.setup.film.part.line',
        ondelete='cascade'
    )

    car_size_id = fields.Many2one(
        'wof.car.size',
        string="حجم السيارة"
    )

    part_price = fields.Float(
        string="سعر الجزء"
    )

    discount_exceed_limit = fields.Integer(
        string="نسبة الخصم المسموح"
    )

    tax_id = fields.Many2one(
        'account.tax',
        string="الضريبة",
        domain=[('type_tax_use', '=', 'sale')]
    )

    price_readonly = fields.Boolean(
        string="السعر ثابت"
    )

    free_part = fields.Boolean(
        string="جزء مجاني"
    )

class WofSetupFilmPartCommissionLine(models.TransientModel):
    _name = 'wof.setup.film.part.commission.line'
    _description = 'WOF Setup Film Part Commission Line'

    part_line_id = fields.Many2one(
        'wof.setup.film.part.line',
        ondelete='cascade'
    )

    car_size_id = fields.Many2one(
        'wof.car.size',
        string="حجم السيارة"
    )

    commission = fields.Float(
        string="عمولة الفني"
    )