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
        ('films', 'الأفلام'),
    ], default='welcome')

    current_service_index = fields.Integer(default=0)

    service_line_ids = fields.One2many(
        'wof.setup.wizard.service.line',
        'wizard_id',
        string="أنواع الخدمات"
    )

    film_line_ids = fields.One2many(
        'wof.setup.wizard.film.line',
        'wizard_id',
        string="الأفلام"
    )

    current_service_line_id = fields.Many2one(
        'wof.setup.wizard.service.line',
        compute="_compute_current_service_line",
        string="الخدمة الحالية"
    )

    current_service_name = fields.Char(
        related='current_service_line_id.custom_name',
        string="الخدمة الحالية"
    )

    selected_services_count = fields.Integer(
        compute="_compute_selected_services_count"
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        lines = []
        seq = 1
        for option_key, option_label in SERVICE_OPTIONS:
            lines.append((0, 0, {
                'sequence': seq,
                'service_options': option_key,
                'custom_name': option_label,
            }))
            seq += 1

        res['service_line_ids'] = lines
        return res

    def _reload_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wof.setup.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.depends('service_line_ids.selected')
    def _compute_selected_services_count(self):
        for rec in self:
            rec.selected_services_count = len(
                rec.service_line_ids.filtered('selected')
            )

    @api.depends(
        'service_line_ids.selected',
        'service_line_ids.sequence',
        'current_service_index'
    )
    def _compute_current_service_line(self):
        for rec in self:
            selected = rec.service_line_ids.filtered('selected').sorted('sequence')
            if selected and rec.current_service_index < len(selected):
                rec.current_service_line_id = selected[rec.current_service_index]
            else:
                rec.current_service_line_id = False

    def action_start_setup(self):
        self.ensure_one()
        self.step = 'service_types'
        return self._reload_wizard()

    def action_back_welcome(self):
        self.ensure_one()
        self.step = 'welcome'
        return self._reload_wizard()

    def action_back_service_types(self):
        self.ensure_one()
        self.step = 'service_types'
        return self._reload_wizard()

    def action_go_films(self):
        self.ensure_one()

        selected_lines = self.service_line_ids.filtered('selected').sorted('sequence')

        if not selected_lines:
            raise ValidationError(_("يجب اختيار نوع خدمة واحد على الأقل."))

        for line in selected_lines:
            if not line.custom_name:
                raise ValidationError(_("يرجى إدخال اسم لكل خدمة مختارة."))

        self.write({
            'step': 'films',
            'current_service_index': 0,
        })

        return self._reload_wizard()

    def action_add_film_line(self):
        self.ensure_one()

        if not self.current_service_line_id:
            raise ValidationError(_("لا توجد خدمة حالية لإضافة فيلم لها."))

        self.write({
            'film_line_ids': [(0, 0, {
                'service_line_id': self.current_service_line_id.id,
                'film_name': '',
                'warranty_years': '5',
                'selected': True,
            })]
        })

        return self._reload_wizard()

    def action_next_service_film(self):
        self.ensure_one()

        selected = self.service_line_ids.filtered('selected').sorted('sequence')
        next_index = self.current_service_index + 1

        if next_index >= len(selected):
            return self.action_go_parts()

        self.current_service_index = next_index
        return self._reload_wizard()

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
        company = self.env.company.parent_id or self.env.company
        ServiceType = self.env['wof.service.type'].sudo()

        service = ServiceType.search([
            ('service_options', '=', service_line.service_options),
            ('company_id', '=', company.id),
        ], limit=1)

        vals = {
            'name': service_line.custom_name,
            'code': self._get_service_code(service_line.service_options),
            'service_options': service_line.service_options,
            'company_id': company.id,
        }

        if service:
            service.write({
                'name': service_line.custom_name,
            })
        else:
            service = ServiceType.create(vals)

        return service

    def action_create_all_setup_records(self):
        self.ensure_one()

        selected_service_lines = self.service_line_ids.filtered('selected')

        if not selected_service_lines:
            raise ValidationError(_("يجب اختيار نوع خدمة واحد على الأقل."))

        company = self.env.company.parent_id or self.env.company
        Film = self.env['wof.film.category'].sudo()

        service_map = {}

        for service_line in selected_service_lines:
            if not service_line.custom_name:
                raise ValidationError(_("يرجى إدخال اسم الخدمة المختارة."))

            service = self._ensure_service_type_from_line(service_line)
            service_map[service_line.id] = service

        for film_line in self.film_line_ids.filtered('selected'):

            if not film_line.film_name:
                raise ValidationError(_("يرجى إدخال اسم الفيلم."))

            service = service_map.get(film_line.service_line_id.id)

            if not service:
                continue

            existing = Film.search([
                ('name', '=', film_line.film_name),
                ('service_type_id', '=', service.id),
                ('company_id', '=', company.id),
            ], limit=1)

            vals = {
                'name': film_line.film_name,
                'service_type_id': service.id,
                'warranty_years': film_line.warranty_years,
                'company_id': company.id,
            }

            if existing:
                existing.write(vals)
            else:
                Film.create(vals)

        return True

    def action_go_parts(self):
        self.ensure_one()

        self.action_create_all_setup_records()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('تم الحفظ'),
                'message': _('تم حفظ الخدمات والأفلام بنجاح. سنكمل صفحة الأجزاء في الخطوة التالية.'),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_finish_setup(self):
        self.ensure_one()

        self.action_create_all_setup_records()

        self.env['ir.config_parameter'].sudo().set_param(
            'yousentech_wo_v4.setup_completed',
            True
        )

        action = self.env.ref(
            'yousentech_wo_v4.action_service_types_wo_v4',
            raise_if_not_found=False
        )

        if action:
            return action.read()[0]

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }


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

    service_options = fields.Selection(
        SERVICE_OPTIONS,
        string="النوع",
        required=False
    )

    custom_name = fields.Char(string="اسم الخدمة")

    is_current = fields.Boolean(
        compute="_compute_is_current"
    )

    @api.depends(
        'wizard_id.current_service_line_id',
        'wizard_id.current_service_index',
        'selected'
    )
    def _compute_is_current(self):
        for rec in self:
            rec.is_current = bool(
                rec.wizard_id
                and rec.wizard_id.current_service_line_id
                and rec.id == rec.wizard_id.current_service_line_id.id
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

    service_line_id = fields.Many2one(
        'wof.setup.wizard.service.line',
        string="نوع الخدمة",
        required=True,
        ondelete='cascade'
    )

    selected = fields.Boolean(
        string="اختيار",
        default=True
    )

    service_name = fields.Char(
        related='service_line_id.custom_name',
        string="نوع الخدمة"
    )

    film_name = fields.Char(
        string="اسم الفيلم",
        required=True
    )

    warranty_years = fields.Char(
        string="سنوات الضمان"
    )