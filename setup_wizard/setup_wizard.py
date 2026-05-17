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


CAR_SIZE_OPTIONS = [
    ('XS', 'صغير جداً'),
    ('S', 'صغير'),
    ('M', 'متوسط'),
    ('L', 'كبير'),
    ('XL', 'كبير جداً'),
    ('SUV', 'دفع رباعي / SUV'),
]


class WofSetupWizard(models.TransientModel):
    _name = 'wof.setup.wizard'
    _description = 'WOF Setup Wizard'

    step = fields.Selection([
        ('welcome', 'الترحيب'),
        ('car_sizes', 'أحجام السيارة'),
        ('service_types', 'أنواع الخدمات'),
    ], default='welcome')

    car_size_line_ids = fields.One2many(
        'wof.setup.wizard.car.size.line',
        'wizard_id',
        string="أحجام السيارة"
    )

    service_line_ids = fields.One2many(
        'wof.setup.wizard.service.line',
        'wizard_id',
        string="أنواع الخدمات"
    )

    @api.model
    def reset_setup_temp_data(self):
        self.env['wof.setup.temp.film.part.commission.line'].sudo().search([]).unlink()
        self.env['wof.setup.temp.film.part.price.line'].sudo().search([]).unlink()
        self.env['wof.setup.temp.film.part'].sudo().search([]).unlink()
        self.env['wof.setup.temp.film'].sudo().search([]).unlink()

        self.env['wof.setup.film.part.commission.line'].sudo().search([]).unlink()
        self.env['wof.setup.film.part.price.line'].sudo().search([]).unlink()
        self.env['wof.setup.film.part.line'].sudo().search([]).unlink()
        self.env['wof.setup.film.wizard'].sudo().search([]).unlink()

        self.env['wof.setup.wizard.service.line'].sudo().search([]).unlink()
        self.env['wof.setup.wizard.car.size.line'].sudo().search([]).unlink()

        old_wizards = self.env['wof.setup.wizard'].sudo().search([])
        old_wizards.unlink()


    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        if 'car_size_line_ids' in fields_list:
            size_lines = []
            sequence = 1
            for code, name in CAR_SIZE_OPTIONS:
                size_lines.append((0, 0, {
                    'sequence': sequence,
                    'selected': code in ['S', 'M', 'L', 'SUV'],
                    'code': code,
                    'name': name,
                }))
                sequence += 1
            res['car_size_line_ids'] = size_lines

        if 'service_line_ids' in fields_list:
            service_lines = []
            sequence = 1
            for option_key, option_label in SERVICE_OPTIONS:
                service_lines.append((0, 0, {
                    'sequence': sequence,
                    'service_options': option_key,
                    'custom_name': option_label,
                }))
                sequence += 1
            res['service_line_ids'] = service_lines

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

    def action_go_service_types(self):
        self.ensure_one()

        selected_sizes = self.car_size_line_ids.filtered('selected')
        if not selected_sizes:
            raise ValidationError(_("يجب اختيار حجم سيارة واحد على الأقل."))

        for line in selected_sizes:
            if not line.name:
                raise ValidationError(_("يرجى إدخال اسم لكل حجم سيارة مختار."))

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

            if existing:
                existing.write(vals)
                size = existing
            else:
                size = CarSize.create(vals)

            size_map[line.id] = size.id

        return size_map
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
            service.write(vals)
        else:
            service = ServiceType.create(vals)

        return service

    def _get_size_key(self, line):
        return line.car_size_line_id.id if line.car_size_line_id else False
    def _get_part_size_ids(self, temp_part):
        size_ids = set()
        size_ids.update(temp_part.price_line_ids.mapped(lambda line: self._get_size_key(line)))
        size_ids.update(temp_part.commission_line_ids.mapped(lambda line: self._get_size_key(line)))
        return size_ids or {False}

    def _get_line_for_size(self, lines, size_id):
        return lines.filtered(lambda line: self._get_size_key(line) == size_id)[:1]

    def _prepare_film_part_line_vals(self, film, temp_part, size_id, size_map):
        price_line = self._get_line_for_size(temp_part.price_line_ids, size_id)
        commission_line = self._get_line_for_size(temp_part.commission_line_ids, size_id)

        real_size_id = size_map.get(size_id) if size_id else False

        return {
            'header_id': film.id,
            'car_part_id': temp_part.car_part_id.id,
            'car_size_id': real_size_id or False,
            'part_price': price_line.part_price if price_line else 0.0,
            'commission': commission_line.commission if commission_line else 0.0,
            'discount_exceed_limit': price_line.discount_exceed_limit if price_line else 0,
            'tax_id': price_line.tax_id.id if price_line and price_line.tax_id else False,
            'price_readonly': price_line.price_readonly if price_line else False,
            'free_part': price_line.free_part if price_line else False,
        }

    def action_finish_all_setup(self):
        self.ensure_one()
        size_map = self.action_save_car_sizes()
        self.action_save_car_sizes()

        selected_services = self.service_line_ids.filtered('selected')
        if not selected_services:
            raise ValidationError(_("يجب اختيار نوع خدمة واحد على الأقل."))

        not_completed = selected_services.filtered(lambda line: not line.completed)
        if not_completed:
            names = ", ".join(not_completed.mapped('custom_name'))
            raise ValidationError(_("الخدمات التالية لم تكتمل تهيئتها:\n%s") % names)

        company = self.env.company.parent_id or self.env.company

        FilmCategory = self.env['wof.film.category'].sudo()
        FilmPartLine = self.env['wof.film.parts.lines'].sudo()
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
                    'warranty_years': temp_film.warranty_years,
                    'company_id': company.id,
                }

                if film:
                    film.write(film_vals)
                else:
                    film = FilmCategory.create(film_vals)

                for temp_part in temp_film.part_line_ids:
                    if not temp_part.car_part_id:
                        continue

                    for size_id in self._get_part_size_ids(temp_part):
                        vals = self._prepare_film_part_line_vals(film, temp_part, size_id, size_map)
                        existing = FilmPartLine.search([
                            ('header_id', '=', film.id),
                            ('car_part_id', '=', temp_part.car_part_id.id),
                            ('car_size_id', '=', size_map.get(size_id) if size_id else False),
                        ], limit=1)

                        if existing:
                            existing.write(vals)
                        else:
                            FilmPartLine.create(vals)

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


class WofSetupWizardCarSizeLine(models.TransientModel):
    _name = 'wof.setup.wizard.car.size.line'
    _description = 'WOF Setup Wizard Car Size Line'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'wof.setup.wizard',
        string="المعالج",
        ondelete='cascade'
    )

    sequence = fields.Integer(
        string="الترتيب",
        default=10
    )

    selected = fields.Boolean(
        string="اختيار",
        default=True
    )

    code = fields.Char(
        string="الكود"
    )

    name = fields.Char(
        string="اسم الحجم"
    )
    def action_open_line(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': _('تعديل حجم السيارة'),
            'res_model': 'wof.setup.wizard.car.size.line',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
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

        return {
            'type': 'ir.actions.act_window',
            'name': _('الأفلام المؤقتة - %s') % (self.custom_name or ''),
            'res_model': 'wof.setup.temp.film',
            'view_mode': 'tree,form',
            'domain': [
                ('wizard_id', '=', self.wizard_id.id),
                ('service_line_id', '=', self.id),
            ],
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
        string="اسم الفيلم"
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

    def _save_current_film_to_temp(self):
        self.ensure_one()

        if not self.film_name:
            raise ValidationError(_("يرجى إدخال اسم الفيلم."))

        TempFilm = self.env['wof.setup.temp.film'].sudo()
        TempPart = self.env['wof.setup.temp.film.part'].sudo()
        TempPrice = self.env['wof.setup.temp.film.part.price.line'].sudo()
        TempCommission = self.env['wof.setup.temp.film.part.commission.line'].sudo()

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
            'warranty_years': self.warranty_years,
        })

        for part in self.part_line_ids.filtered('selected'):

            if not part.car_part_id:
                raise ValidationError(_("يرجى اختيار الجزء."))

            temp_part = TempPart.create({
                'film_id': temp_film.id,
                'car_part_id': part.car_part_id.id,
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

        self._save_current_film_to_temp()

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

        self._save_current_film_to_temp()

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
        self.ensure_one()

        if not self.service_options:
            raise ValidationError(_("لم يتم تحديد نوع الخدمة."))

        Parts = self.env['wof.car.parts'].sudo()

        parts = Parts.search([
            ('service_options', '=', self.service_options),
        ], order='name')

        if not parts:
            raise ValidationError(
                _("لا توجد أجزاء معرفة لهذا النوع من الخدمة.")
            )

        existing_parts = self.part_line_ids.mapped('car_part_id')

        commands = []
        for part in parts:
            if part not in existing_parts:
                commands.append((0, 0, {
                    'selected': True,
                    'car_part_id': part.id,
                }))

        if not commands:
            raise ValidationError(
                _("كل الأجزاء الخاصة بهذا النوع مضافة مسبقاً.")
            )

        self.write({
            'part_line_ids': commands
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('تهيئة أنواع %s') % (self.service_name or ''),
            'res_model': 'wof.setup.film.wizard',
            'res_id': self.id,
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

    def _format_size_name(self, line):
        return line.car_size_line_id.display_name if line.car_size_line_id else _('كل الأحجام')

    @api.depends(
        'price_line_ids.car_size_line_id',
        'price_line_ids.part_price',
        'commission_line_ids.car_size_line_id',
        'commission_line_ids.commission', )
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
            self.write({
                'price_line_ids': commands
            })


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
            self.write({
                'commission_line_ids': commands
            })


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

class WofSetupFilmPartPriceLine(models.TransientModel):
    _name = 'wof.setup.film.part.price.line'
    _description = 'WOF Setup Film Part Price Line'
    _order = 'id'

    part_line_id = fields.Many2one(
        'wof.setup.film.part.line',
        string="سطر الجزء",
        ondelete='cascade'
    )

    car_size_line_id = fields.Many2one(
        'wof.setup.wizard.car.size.line',
        string="حجم السيارة",
        domain="[('wizard_id', '=', parent_wizard_id), ('selected', '=', True)]"
    )

    parent_wizard_id = fields.Many2one(
        related='part_line_id.wizard_id.parent_wizard_id',
        store=False
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
                raise ValidationError(
                    _("لا يمكن تكرار نفس حجم السيارة في تسعير الجزء.")
                )

class WofSetupFilmPartCommissionLine(models.TransientModel):
    _name = 'wof.setup.film.part.commission.line'
    _description = 'WOF Setup Film Part Commission Line'
    _order = 'id'

    part_line_id = fields.Many2one(
        'wof.setup.film.part.line',
        string="سطر الجزء",
        ondelete='cascade'
    )

    car_size_line_id = fields.Many2one(
        'wof.setup.wizard.car.size.line',
        string="حجم السيارة",
        domain="[('wizard_id', '=', parent_wizard_id), ('selected', '=', True)]"
    )

    parent_wizard_id = fields.Many2one(
        related='part_line_id.wizard_id.parent_wizard_id',
        store=False
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
                raise ValidationError(
                    _("لا يمكن تكرار نفس حجم السيارة في تسعير العمولة.")
                )

class WofSetupTempFilm(models.TransientModel):
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

    film_name = fields.Char(string="اسم الفيلم")
    warranty_years = fields.Char(string="سنوات الضمان")

    part_line_ids = fields.One2many(
        'wof.setup.temp.film.part',
        'film_id',
        string="الأجزاء"
    )


class WofSetupTempFilmPart(models.TransientModel):
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


class WofSetupTempFilmPartPriceLine(models.TransientModel):
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


class WofSetupTempFilmPartCommissionLine(models.TransientModel):
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