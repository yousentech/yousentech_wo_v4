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
        ('parts', 'الأجزاء'),
    ], default='welcome')

    current_service_index = fields.Integer(default=0)
    current_film_index = fields.Integer(default=0)

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

    part_line_ids = fields.One2many(
        'wof.setup.wizard.part.line',
        'wizard_id',
        string="الأجزاء"
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

    current_film_line_id = fields.Many2one(
        'wof.setup.wizard.film.line',
        compute="_compute_current_film_line",
        string="الفيلم الحالي"
    )

    current_film_name = fields.Char(
        related='current_film_line_id.film_name',
        string="الفيلم الحالي"
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

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

    # =========================
    # HELPERS
    # =========================

    def _reload_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wof.setup.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _selected_service_lines(self):
        self.ensure_one()
        return self.service_line_ids.filtered('selected').sorted('sequence')

    def _get_current_service_line(self):
        self.ensure_one()
        selected = self._selected_service_lines()

        if selected and self.current_service_index < len(selected):
            return selected[self.current_service_index]

        return self.env['wof.setup.wizard.service.line']

    def _get_current_service_films(self):
        self.ensure_one()
        current_service = self._get_current_service_line()

        if not current_service:
            return self.env['wof.setup.wizard.film.line']

        return self.film_line_ids.filtered(
            lambda line: line.selected and line.service_line_id == current_service
        ).sorted('sequence')

    def _get_current_film_line(self):
        self.ensure_one()
        films = self._get_current_service_films()

        if films and self.current_film_index < len(films):
            return films[self.current_film_index]

        return self.env['wof.setup.wizard.film.line']

    def _refresh_display_flags(self):
        """
        مهم جداً:
        هذا يحل مشكلة ظهور أفلام خدمة داخل خدمة ثانية.
        لا نعتمد على domain ديناميكي فقط.
        """
        self.ensure_one()

        current_service = self._get_current_service_line()
        current_film = self._get_current_film_line()

        if self.film_line_ids:
            self.film_line_ids.write({
                'display_in_current_service': False,
            })

        if current_service:
            self.film_line_ids.filtered(
                lambda line: line.service_line_id == current_service
            ).write({
                'display_in_current_service': True,
            })

        if self.part_line_ids:
            self.part_line_ids.write({
                'display_in_current_film': False,
            })

        if current_film:
            self.part_line_ids.filtered(
                lambda line: line.film_line_id == current_film
            ).write({
                'display_in_current_film': True,
            })

    # =========================
    # COMPUTES
    # =========================

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

    @api.depends(
        'film_line_ids.selected',
        'film_line_ids.service_line_id',
        'film_line_ids.sequence',
        'current_service_line_id',
        'current_film_index'
    )
    def _compute_current_film_line(self):
        for rec in self:
            films = rec.film_line_ids.filtered(
                lambda line: line.selected and line.service_line_id == rec.current_service_line_id
            ).sorted('sequence')

            if films and rec.current_film_index < len(films):
                rec.current_film_line_id = films[rec.current_film_index]
            else:
                rec.current_film_line_id = False

    # =========================
    # NAVIGATION
    # =========================

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

    def action_back_films(self):
        self.ensure_one()
        self.write({
            'step': 'films',
            'current_film_index': 0,
        })
        self._refresh_display_flags()
        return self._reload_wizard()

    def action_go_films(self):
        self.ensure_one()

        selected = self._selected_service_lines()
        if not selected:
            raise ValidationError(_("يجب اختيار نوع خدمة واحد على الأقل."))

        for line in selected:
            if not line.custom_name:
                raise ValidationError(_("يرجى إدخال اسم لكل خدمة مختارة."))

        self.write({
            'step': 'films',
            'current_service_index': 0,
            'current_film_index': 0,
        })

        self._refresh_display_flags()
        return self._reload_wizard()

    def action_go_parts(self):
        self.ensure_one()

        selected_films = self.film_line_ids.filtered('selected')

        if not selected_films:
            raise ValidationError(_("يجب إضافة فيلم واحد على الأقل قبل إضافة الأجزاء."))

        for film in selected_films:
            if not film.film_name:
                raise ValidationError(_("يرجى إدخال اسم الفيلم."))

        selected_services = self._selected_service_lines()
        first_service_index = 0

        for index, service_line in enumerate(selected_services):
            films = self.film_line_ids.filtered(
                lambda line: line.selected and line.service_line_id == service_line
            )

            if films:
                first_service_index = index
                break

        self.write({
            'step': 'parts',
            'current_service_index': first_service_index,
            'current_film_index': 0,
        })

        self._refresh_display_flags()
        return self._reload_wizard()

    # =========================
    # FILMS
    # =========================

    def action_add_film_line(self):
        self.ensure_one()

        current_service = self._get_current_service_line()

        if not current_service:
            raise ValidationError(_("لا توجد خدمة حالية لإضافة فيلم لها."))

        current_films = self.film_line_ids.filtered(
            lambda line: line.service_line_id == current_service
        )

        next_sequence = max(current_films.mapped('sequence') or [0]) + 1

        self.write({
            'film_line_ids': [(0, 0, {
                'sequence': next_sequence,
                'service_line_id': current_service.id,
                'film_name': '',
                'warranty_years': '5',
                'selected': True,
                'display_in_current_service': True,
            })]
        })

        self._refresh_display_flags()
        return self._reload_wizard()

    def action_next_service_film(self):
        self.ensure_one()

        selected = self._selected_service_lines()
        next_index = self.current_service_index + 1

        if next_index >= len(selected):
            return self.action_go_parts()

        self.write({
            'current_service_index': next_index,
            'current_film_index': 0,
        })

        self._refresh_display_flags()
        return self._reload_wizard()

    # =========================
    # PARTS
    # =========================

    def action_add_part_line(self):
        self.ensure_one()

        current_service = self._get_current_service_line()
        current_film = self._get_current_film_line()

        if not current_service:
            raise ValidationError(_("لا توجد خدمة حالية."))

        if not current_film:
            raise ValidationError(_("لا يوجد فيلم حالي لإضافة الأجزاء له."))

        current_parts = self.part_line_ids.filtered(
            lambda line: line.film_line_id == current_film
        )

        next_sequence = max(current_parts.mapped('sequence') or [0]) + 1

        self.write({
            'part_line_ids': [(0, 0, {
                'sequence': next_sequence,
                'service_line_id': current_service.id,
                'film_line_id': current_film.id,
                'selected': True,
                'display_in_current_film': True,
            })]
        })

        self._refresh_display_flags()
        return self._reload_wizard()

    def action_next_film_part(self):
        self.ensure_one()

        selected_services = self._selected_service_lines()
        current_films = self._get_current_service_films()

        next_film_index = self.current_film_index + 1

        # نفس الخدمة، الفيلم التالي
        if next_film_index < len(current_films):
            self.current_film_index = next_film_index
            self._refresh_display_flags()
            return self._reload_wizard()

        # الخدمة التالية التي لديها أفلام
        next_service_index = self.current_service_index + 1

        while next_service_index < len(selected_services):
            next_service = selected_services[next_service_index]

            service_films = self.film_line_ids.filtered(
                lambda line: line.selected and line.service_line_id == next_service
            ).sorted('sequence')

            if service_films:
                self.write({
                    'current_service_index': next_service_index,
                    'current_film_index': 0,
                })
                self._refresh_display_flags()
                return self._reload_wizard()

            next_service_index += 1

        return self.action_finish_setup()

    # =========================
    # CREATE MAIN RECORDS
    # =========================

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

        selected_service_lines = self._selected_service_lines()
        if not selected_service_lines:
            raise ValidationError(_("يجب اختيار نوع خدمة واحد على الأقل."))

        company = self.env.company.parent_id or self.env.company

        Film = self.env['wof.film.category'].sudo()
        FilmPartLine = self.env['wof.film.parts.lines'].sudo()

        service_map = {}
        film_map = {}

        for service_line in selected_service_lines:
            if not service_line.custom_name:
                raise ValidationError(_("يرجى إدخال اسم الخدمة المختارة."))

            service = self._ensure_service_type_from_line(service_line)
            service_map[service_line.id] = service

        for film_line in self.film_line_ids.filtered('selected').sorted('sequence'):

            if not film_line.film_name:
                raise ValidationError(_("يرجى إدخال اسم الفيلم."))

            service = service_map.get(film_line.service_line_id.id)
            if not service:
                continue

            existing_film = Film.search([
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

            if existing_film:
                existing_film.write(vals)
                film = existing_film
            else:
                film = Film.create(vals)

            film_map[film_line.id] = film

        for part_line in self.part_line_ids.filtered('selected').sorted('sequence'):

            if not part_line.car_part_id:
                raise ValidationError(_("يرجى اختيار الجزء."))

            film = film_map.get(part_line.film_line_id.id)
            if not film:
                continue

            domain = [
                ('header_id', '=', film.id),
                ('car_part_id', '=', part_line.car_part_id.id),
            ]

            if part_line.car_size_id:
                domain.append(('car_size_id', '=', part_line.car_size_id.id))
            else:
                domain.append(('car_size_id', '=', False))

            existing_part = FilmPartLine.search(domain, limit=1)

            vals = {
                'header_id': film.id,
                'car_part_id': part_line.car_part_id.id,
                'car_size_id': part_line.car_size_id.id if part_line.car_size_id else False,
                'part_price': part_line.part_price,
                'commission': part_line.commission,
                'discount_exceed_limit': part_line.discount_exceed_limit,
                'tax_id': part_line.tax_id.id if part_line.tax_id else False,
                'price_readonly': part_line.price_readonly,
                'free_part': part_line.free_part,
            }

            if existing_part:
                existing_part.write(vals)
            else:
                FilmPartLine.create(vals)

        return True

    def action_finish_setup(self):
        self.ensure_one()

        self.action_create_all_setup_records()

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
        compute="_compute_is_current",
        string="الخدمة الحالية"
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
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)

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

    display_in_current_service = fields.Boolean(
        string="يعرض في الخدمة الحالية",
        default=False
    )

    service_name = fields.Char(
        related='service_line_id.custom_name',
        string="نوع الخدمة"
    )

    film_name = fields.Char(string="اسم الفيلم")

    warranty_years = fields.Char(string="سنوات الضمان")

    is_current = fields.Boolean(
        compute="_compute_is_current",
        string="الفيلم الحالي"
    )

    @api.depends(
        'wizard_id.current_film_line_id',
        'wizard_id.current_film_index',
        'selected'
    )
    def _compute_is_current(self):
        for rec in self:
            rec.is_current = bool(
                rec.wizard_id
                and rec.wizard_id.current_film_line_id
                and rec.id == rec.wizard_id.current_film_line_id.id
            )


class WofSetupWizardPartLine(models.TransientModel):
    _name = 'wof.setup.wizard.part.line'
    _description = 'WOF Setup Wizard Part Line'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)

    wizard_id = fields.Many2one(
        'wof.setup.wizard',
        string="المعالج",
        ondelete='cascade'
    )

    service_line_id = fields.Many2one(
        'wof.setup.wizard.service.line',
        string="الخدمة المؤقتة",
        required=True,
        ondelete='cascade'
    )

    film_line_id = fields.Many2one(
        'wof.setup.wizard.film.line',
        string="الفيلم المؤقت",
        required=True,
        ondelete='cascade'
    )

    selected = fields.Boolean(
        string="اختيار",
        default=True
    )

    display_in_current_film = fields.Boolean(
        string="يعرض في الفيلم الحالي",
        default=False
    )

    service_name = fields.Char(
        related='service_line_id.custom_name',
        string="الخدمة"
    )

    film_name = fields.Char(
        related='film_line_id.film_name',
        string="الفيلم"
    )

    car_part_id = fields.Many2one(
        'wof.car.parts',
        string="الجزء"
    )

    car_size_id = fields.Many2one(
        'wof.car.size',
        string="حجم السيارة"
    )

    part_price = fields.Float(string="سعر الجزء")
    commission = fields.Float(string="عمولة الفني")
    discount_exceed_limit = fields.Integer(string="نسبة الخصم المسموح")

    tax_id = fields.Many2one(
        'account.tax',
        string="الضريبة",
        domain=[('type_tax_use', '=', 'sale')]
    )

    price_readonly = fields.Boolean(string="السعر ثابت")
    free_part = fields.Boolean(string="جزء مجاني")