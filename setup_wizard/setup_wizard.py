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


class WofSetupWizard(models.TransientModel):
    _name = 'wof.setup.wizard'
    _description = 'WOF Setup Wizard'

    step = fields.Selection([
        ('welcome', 'الترحيب'),
        ('car_sizes', 'أحجام السيارة'),
        ('tint_degrees', 'درجات اللون'),
        ('service_types', 'أنواع الخدمات'),
    ], default='welcome')

    car_size_line_ids = fields.One2many(
        'wof.setup.wizard.car.size.line',
        'wizard_id',
        string="أحجام السيارة"
    )

    tint_degree_method = fields.Selection(
        TINT_DEGREE_METHODS,
        string="طريقة درجات اللون",
        default='percent',
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

        if 'tint_degree_line_ids' in fields_list:
            method = res.get('tint_degree_method') or 'percent'
            values = TINT_DEGREE_PRESETS.get(method, [])
            degree_lines = []

            for index, item in enumerate(values, start=1):
                label, value = item
                degree_lines.append((0, 0, {
                    'sequence': index,
                    'selected': True,
                    'name': label,
                    'value': value,
                }))

            res['tint_degree_line_ids'] = degree_lines

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
                    'selected': True,
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

    def _create_film_tint_degrees(self, film, temp_film, degree_map):
        self.ensure_one()

        if film.service_options != 'tint':
            return

        FilmLine = self.env['wof.film.category.lines'].sudo()

        for degree in temp_film.tint_degree_line_ids.filtered('selected').sorted('sequence'):
            real_degree_id = degree_map.get(degree.setup_degree_line_id.id)

            existing = FilmLine.search([
                ('header_id', '=', film.id),
                ('degree_value', '=', degree.value),
            ], limit=1)

            vals = {
                'header_id': film.id,
                'sequence': degree.sequence,
                'tint_degree_id': real_degree_id or False,
                'name': degree.value,
                'degree_label': degree.name,
                'degree_value': degree.value,
            }

            if existing:
                existing.write(vals)
            else:
                FilmLine.create(vals)

    def action_finish_all_setup(self):
        self.ensure_one()

        size_map = self.action_save_car_sizes()
        degree_map = self.action_save_tint_degrees()

        selected_services = self.service_line_ids.filtered('selected')
        if not selected_services:
            raise ValidationError(_("يجب اختيار نوع خدمة واحد على الأقل."))

        not_completed = selected_services.filtered(lambda line: not line.completed)
        if not_completed:
            names = ", ".join(not_completed.mapped('custom_name'))
            raise ValidationError(_("الخدمات التالية لم تكتمل تهيئتها:\n%s") % names)

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
class WofSetupWizardCarSizeLine(models.TransientModel):
    _name = 'wof.setup.wizard.car.size.line'
    _description = 'WOF Setup Wizard Car Size Line'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'wof.setup.wizard',
        string="المعالج",
        ondelete='cascade'
    )

    sequence = fields.Integer(string="الترتيب", default=10)
    selected = fields.Boolean(string="اختيار", default=True)
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


class WofSetupWizardTintDegreeLine(models.TransientModel):
    _name = 'wof.setup.wizard.tint.degree.line'
    _description = 'WOF Setup Wizard Tint Degree Line'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'wof.setup.wizard',
        string="المعالج",
        ondelete='cascade'
    )

    sequence = fields.Integer(string="الترتيب", default=10)
    selected = fields.Boolean(string="اختيار", default=True)
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

        setup._prepare_tint_degree_lines()

        return {
            'type': 'ir.actions.act_window',
            'name': _('تهيئة أنواع %s') % (self.custom_name or ''),
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
        ('info', 'بيانات النوع'),
        ('degrees', 'درجات اللون'),
        ('parts', 'الأجزاء'),
        ('service_areas', 'مناطق الخدمة'),
    ], default='info', string="مرحلة التهيئة")

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


    def action_film_next_degrees(self):
        self.ensure_one()

        if not self.film_name:
            raise ValidationError(_("يرجى إدخال اسم النوع."))

        if self.service_options == 'tint':
            self._prepare_tint_degree_lines()
            self.film_step = 'degrees'
        else:
            self.film_step = 'parts'
            self.parts_mode = 'parts'
            self._load_service_parts_to_lines('car_part')

        return self._reload_film_wizard()


    def action_film_back_info(self):
        self.ensure_one()
        self.film_step = 'info'
        return self._reload_film_wizard()
   
    def action_go_service_areas(self):
        self.ensure_one()

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

        self.film_step = 'parts'
        self.parts_mode = 'parts'
        self._load_service_parts_to_lines('car_part')

        return self._reload_film_wizard()
  
    def _load_service_parts_to_lines(self, part_type='car_part'):
        self.ensure_one()

        if not self.service_options:
            return False

        if part_type not in ('car_part', 'service_area'):
            part_type = 'car_part'

        # حذف السطور الفارغة لنفس النوع فقط؛ لا نلمس النوع الآخر.
        empty_lines = self.part_line_ids.filtered(
            lambda line: line.line_role == part_type and not line.car_part_id
        )
        if empty_lines:
            empty_lines.unlink()

        Parts = self.env['wof.car.parts'].sudo()
        parts = Parts.search([
            ('service_options', '=', self.service_options),
            ('part_type', '=', part_type),
            ('active', '=', True),
        ], order='priority_part, name')

        existing_parts = self.part_line_ids.filtered(
            lambda line: line.line_role == part_type
        ).mapped('car_part_id')

        commands = []
        for part in parts:
            if part not in existing_parts:
                commands.append((0, 0, {
                    'selected': True,
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

        self.write({
            'film_name': False,
            'warranty_duration': 10,
            'warranty_period': 'year',
            'film_step': 'info',
            'part_line_ids': [(5, 0, 0)],
            'tint_degree_line_ids': [(5, 0, 0)],
        })

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

class WofSetupFilmTintDegreeLine(models.TransientModel):
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
    service_options = fields.Selection(
        related='wizard_id.service_options',
        store=False
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


class WofSetupFilmPartPriceLine(models.TransientModel):
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


class WofSetupFilmPartCommissionLine(models.TransientModel):
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


class WofSetupTempFilmTintDegreeLine(models.TransientModel):
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
    line_role = fields.Selection([
        ('car_part', 'جزء سيارة'),
        ('service_area', 'منطقة خدمة'),
    ], string="نوع السطر", default='car_part')

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
        required=True
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
        ], limit=1)

        if existing:
            raise ValidationError(_("هذا الجزء موجود مسبقاً."))

        company = self.env.company.parent_id or self.env.company

        vals = {
            'name': self.name,
            'code': self.code,
            'priority_part': self.priority_part,
            'company_id': company.id,
            'service_area_commission_method': self.service_area_commission_method if self.part_type == 'service_area' else False,
            'service_options': setup.service_options,
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