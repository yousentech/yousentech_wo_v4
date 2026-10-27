# -*- coding: utf-8 -*-
"""Service layer for the films & services page and the guided film editor.

OWL client actions:
* ``wof_films_hub``   — one page, a tab per activity, a card per film with readiness.
* ``wof_film_editor`` — six guided steps: basics, tint, components, policies,
  prices & commissions (summary + matrix), review & activation.

All writes go through the persistent records (``wof.film.category`` and its
lines) with the normal ORM access rules; no ``sudo``.
"""

import re
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

WARRANTY_UNITS = [('day', 'يوم'), ('month', 'شهر'), ('year', 'سنة')]
BASIC_FIELDS = {
    'name', 'code', 'description', 'item_type', 'warranty_period', 'warranty_unit',
    'is_effected_in_inventory', 'car_film_product_required', 'warning_msg',
}


class WofFilmCategoryFlow(models.Model):
    _inherit = 'wof.film.category'

    warranty_period = fields.Integer(string='مدة الضمان', default=1)
    warranty_unit = fields.Selection(WARRANTY_UNITS, string='وحدة الضمان', default='year', required=True)

    _sql_constraints = [
        ('film_warranty_period_nonnegative', 'check(warranty_period >= 0)',
         'مدة الضمان لا يمكن أن تكون سالبة.'),
    ]

    # ---------------------------------------------------------------- warranty
    @api.model
    def _wof_warranty_years(self, period, unit):
        period = int(period or 0)
        if unit == 'year':
            return period
        if unit == 'month':
            return period // 12
        return 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._wof_sync_warranty_vals(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._wof_sync_warranty_vals(vals)
        return super().write(vals)

    @api.model
    def _wof_sync_warranty_vals(self, vals):
        """Keep the legacy ``warranty_years`` and the new period/unit in step."""
        if 'warranty_period' in vals or 'warranty_unit' in vals:
            period = vals.get('warranty_period', self[:1].warranty_period if self else 1)
            unit = vals.get('warranty_unit', self[:1].warranty_unit if self else 'year')
            vals['warranty_years'] = self._wof_warranty_years(period, unit)
        elif 'warranty_years' in vals:
            vals.update({'warranty_period': vals['warranty_years'] or 0, 'warranty_unit': 'year'})

    def _wof_warranty_label(self):
        self.ensure_one()
        if not self.warranty_period:
            return _('بدون ضمان')
        return '%s %s' % (self.warranty_period, dict(WARRANTY_UNITS).get(self.warranty_unit, ''))

    # ----------------------------------------------------------------- access
    @api.model
    def _wof_flow_can_read(self):
        if not self.env.user.has_group('yousentech_wo_v4.group_wo_manager'):
            raise AccessError(_('شاشة الأفلام والخدمات متاحة لمدير مركز العناية.'))
        self.check_access_rights('read')

    @api.model
    def _wof_profile(self, company=None):
        company = company or self.env.company
        return self.env['wof.company.profile'].search([('company_id', '=', company.id)], limit=1)

    # -------------------------------------------------------------- readiness
    def _wof_line_complete(self, lines, policy, sizes, prices=False):
        if prices:
            # A zero price is not a price; only the free flag makes a line cost nothing.
            lines = lines.filtered(lambda line: line.free_part or line.part_price > 0)
        by_size = self._wof_line_by_size(lines)
        if policy == 'by_size':
            return bool(sizes) and all(size.id in by_size for size in sizes)
        return 0 in by_size

    def _wof_readiness(self):
        self.ensure_one()
        sizes = self._wof_matrix_sizes()
        lines = self._wof_commercial_lines()
        price_policy = self.pricing_policy or 'fixed'
        price_done = comm_done = 0
        line_states = {}
        for line in lines:
            price_ok = self._wof_line_complete(line.price_line_ids, price_policy, sizes, prices=True)
            comm_lines = line.commission_line_ids
            if line.part_type == 'service_area' and line.service_commission_source == 'from_parts':
                comm_ok = bool(comm_lines)
            else:
                comm_policy = line.commission_calculation_policy or self.commission_calculation_policy or 'fixed'
                comm_ok = self._wof_line_complete(comm_lines, comm_policy, sizes)
            price_done += price_ok
            comm_done += comm_ok
            line_states[line.id] = {'price': price_ok, 'commission': comm_ok}
        needs_tint = self.supports_color_grades and self.item_type == 'film'
        grade_count = len(self.film_category_line_ids.filtered('active'))
        checks = [
            {'key': 'components', 'ok': bool(lines), 'soft': False,
             'note': _('%s مكوّنات') % len(lines) if lines else _('أضف مكوّنًا واحدًا على الأقل')},
            {'key': 'tint', 'ok': (not needs_tint) or grade_count > 0, 'soft': False,
             'note': (_('%s درجات') % grade_count) if needs_tint else _('غير مطلوبة')},
            {'key': 'prices', 'ok': bool(lines) and price_done == len(lines), 'soft': False,
             'note': _('%s من %s مكتملة') % (price_done, len(lines))},
            {'key': 'commissions', 'ok': bool(lines) and comm_done == len(lines), 'soft': True,
             'note': _('%s من %s · لا تمنع التفعيل') % (comm_done, len(lines))},
        ]
        hard = [check for check in checks if not check['soft']]
        return {
            'checks': checks,
            'ready': all(check['ok'] for check in hard),
            'missing': [check['key'] for check in hard if not check['ok']],
            'components': len(lines), 'grades': grade_count, 'needs_tint': needs_tint,
            'price_done': price_done, 'comm_done': comm_done, 'lines': line_states,
        }

    # -------------------------------------------------------------------- hub
    def _wof_card(self):
        self.ensure_one()
        readiness = self._wof_readiness()
        return {
            'id': self.id, 'activity_id': self.service_type_id.id, 'name': self.name,
            'code': self.code, 'item_type': self.item_type, 'description': self.description or '',
            'active': self.active, 'ready': readiness['ready'], 'missing': readiness['missing'],
            'components': readiness['components'], 'grades': readiness['grades'],
            'needs_tint': readiness['needs_tint'],
            'price_done': readiness['price_done'], 'comm_done': readiness['comm_done'],
        }

    @api.model
    def wof_films_hub_load(self):
        self._wof_flow_can_read()
        company = self.env.company
        activities = self.env['wof.service.type'].search([
            ('company_id', '=', company.id), ('active', '=', True),
        ], order='code, name')
        films = self.with_context(active_test=False).search([
            ('company_id', '=', company.id), ('service_type_id', 'in', activities.ids),
        ], order='sequence, name')
        return {
            'can_edit': self.check_access_rights('write', raise_exception=False),
            'activities': [{
                'id': activity.id, 'name': activity.name,
                'supports_grades': bool(activity.supports_color_grades),
            } for activity in activities],
            'films': [film._wof_card() for film in films],
        }

    # ------------------------------------------------------------- create/copy
    @api.model
    def _wof_new_code(self, name, company):
        base = re.sub(r'[^A-Z0-9_.-]+', '-', (name or '').strip().upper()).strip('-')
        if not base:
            base = 'FS-%s' % datetime.now().strftime('%Y%m%d%H%M%S')
        candidate, suffix = base[:40], 1
        Film = self.with_context(active_test=False)
        while Film.search_count([('company_id', '=', company.id), ('code', '=', candidate)]):
            suffix += 1
            candidate = '%s-%s' % (base[:34], suffix)
        return candidate

    @api.model
    def _wof_system_policy_vals(self, profile):
        sizes = self.env['wof.car.size'].search([
            ('company_id', '=', profile.company_id.id), ('active', '=', True),
        ])
        return {
            'use_system_pricing_policy': True, 'pricing_policy': profile.operation_pricing_policy or 'fixed',
            'use_system_car_sizes': True, 'car_size_ids': [(6, 0, sizes.ids)],
            'use_system_commission_policy': True, 'commission_event': profile.commission_event or 'delivery',
            'commission_calculation_policy': 'by_size' if profile.advanced_commission else 'fixed',
            'use_system_tax_policy': True, 'tax_enabled': profile.operation_tax_enabled,
            'tax_id': profile.operation_tax_id.id or False,
            'price_input_mode': profile.operation_price_input_mode or 'excluded',
            'use_system_discount_policy': True, 'discount_enabled': profile.discount_enabled,
            'discount_limit': profile.discount_default_limit,
        }

    @api.model
    def _wof_target_activity(self, activity_id):
        activity = self.env['wof.service.type'].browse(int(activity_id or 0)).exists()
        if not activity or activity.company_id not in self.env.companies or not activity.active:
            raise ValidationError(_('النشاط المحدد غير متاح.'))
        return activity

    @api.model
    def wof_film_create(self, activity_id, name, item_type='film'):
        self._wof_flow_can_read()
        self.check_access_rights('create')
        activity = self._wof_target_activity(activity_id)
        name = (name or '').strip()
        if not name:
            raise ValidationError(_('أدخل اسم الفيلم أو الخدمة.'))
        if item_type not in ('film', 'service'):
            item_type = 'film'
        profile = self._wof_profile(activity.company_id)
        vals = {
            'name': name, 'code': self._wof_new_code(name, activity.company_id),
            'service_type_id': activity.id, 'item_type': item_type, 'active': False,
            'warranty_period': 1, 'warranty_unit': 'year',
            'is_effected_in_inventory': bool(profile.use_inventory) if profile else False,
        }
        if profile:
            vals.update(self._wof_system_policy_vals(profile))
        film = self.create(vals)
        if film.supports_color_grades and item_type == 'film':
            film._wof_apply_tint(use_all=True)
        return film.id

    @api.model
    def wof_film_copy(self, source_id, activity_id, name, options=None):
        """Copy a film into ``activity_id``; ``options`` picks what to copy."""
        self._wof_flow_can_read()
        self.check_access_rights('create')
        options = options or {}
        source = self.with_context(active_test=False).browse(int(source_id or 0)).exists()
        if not source or source.company_id not in self.env.companies:
            raise ValidationError(_('الفيلم المصدر غير متاح.'))
        source.check_access_rule('read')
        activity = self._wof_target_activity(activity_id)
        if activity.company_id != source.company_id:
            raise ValidationError(_('لا يمكن النسخ بين شركتين مختلفتين.'))
        name = (name or '').strip()
        if not name:
            raise ValidationError(_('أدخل اسم الفيلم أو الخدمة الجديد.'))
        profile = self._wof_profile(activity.company_id)
        vals = {
            'name': name, 'code': self._wof_new_code(name, activity.company_id),
            'service_type_id': activity.id, 'item_type': source.item_type, 'active': False,
            'description': source.description, 'warranty_period': source.warranty_period,
            'warranty_unit': source.warranty_unit,
            'is_effected_in_inventory': source.is_effected_in_inventory,
            'car_film_product_required': source.car_film_product_required,
            'warning_msg': source.warning_msg,
        }
        if options.get('policies'):
            vals.update({
                'use_system_pricing_policy': source.use_system_pricing_policy,
                'pricing_policy': source.pricing_policy,
                'use_system_car_sizes': source.use_system_car_sizes,
                'car_size_ids': [(6, 0, source.car_size_ids.ids)],
                'use_system_commission_policy': source.use_system_commission_policy,
                'commission_event': source.commission_event,
                'commission_calculation_policy': source.commission_calculation_policy,
                'use_system_tax_policy': source.use_system_tax_policy,
                'tax_enabled': source.tax_enabled, 'tax_id': source.tax_id.id or False,
                'price_input_mode': source.price_input_mode,
                'use_system_discount_policy': source.use_system_discount_policy,
                'discount_enabled': source.discount_enabled, 'discount_limit': source.discount_limit,
            })
        elif profile:
            vals.update(self._wof_system_policy_vals(profile))
        film = self.create(vals)

        grade_map = {}
        with_grades = film.supports_color_grades and film.item_type == 'film'
        if with_grades:
            if options.get('tint') and source.supports_color_grades:
                Grade = self.env['wof.film.category.lines']
                for grade in source.film_category_line_ids.filtered('active'):
                    grade_map[grade.id] = Grade.create({
                        'header_id': film.id, 'sequence': grade.sequence, 'name': grade.name,
                        'code': grade.code, 'transmission_percent': grade.transmission_percent,
                        'product_id': grade.product_id.id or False,
                    })
                film.use_system_tint_grades = source.use_system_tint_grades
            else:
                film._wof_apply_tint(use_all=True)

        if options.get('components'):
            Line = self.env['wof.film.parts.lines']
            Price = self.env['wof.film.parts.price.lines']
            Commission = self.env['wof.film.parts.commission.lines']
            for line in source.film_part_line_ids.sorted(lambda rec: (rec.sequence, rec.id)):
                line_vals = {
                    'header_id': film.id, 'car_part_id': line.car_part_id.id,
                    'sequence': line.sequence, 'part_selected': line.part_selected,
                    'service_commission_source': line.service_commission_source,
                    'commission_calculation_policy': line.commission_calculation_policy,
                    'commission_value_type': line.commission_value_type,
                    'commission_readonly': line.commission_readonly,
                    'technician_commission_distribution': line.technician_commission_distribution,
                    'discount_policy': line.discount_policy, 'discount_limit': line.discount_limit,
                }
                if grade_map and line.part_type == 'car_part':
                    default = grade_map.get(line.film_category_line_id.id)
                    allowed = [grade_map[g.id].id for g in line.allowed_grade_ids if g.id in grade_map]
                    line_vals.update({
                        'film_category_line_id': default.id if default else False,
                        'allowed_grade_ids': [(6, 0, allowed)],
                    })
                new_line = Line.create(line_vals)
                if options.get('prices'):
                    for price in line.price_line_ids:
                        Price.create({
                            'part_line_id': new_line.id, 'car_size_id': price.car_size_id.id or False,
                            'part_price': price.part_price, 'free_part': price.free_part,
                            'price_readonly': price.price_readonly, 'tax_id': price.tax_id.id or False,
                            'discount_exceed_limit': price.discount_exceed_limit,
                        })
                if options.get('commissions'):
                    for commission in line.commission_line_ids:
                        Commission.create({
                            'part_line_id': new_line.id, 'car_size_id': commission.car_size_id.id or False,
                            'commission': commission.commission,
                        })
        return film.id

    # ----------------------------------------------------------------- editor
    def _wof_system_shades(self):
        profile = self._wof_profile(self.company_id)
        if not profile:
            return self.env['wof.setup.tint.shade.line'], profile
        return profile.tint_shade_line_ids.filtered('selected').sorted(lambda rec: (rec.sequence, rec.id)), profile

    def _wof_selected_shade_codes(self, shades=None):
        """System shade codes this film offers today, matched by code or by name
        (grades created by older versions may carry a different code)."""
        self.ensure_one()
        if shades is None:
            shades, _profile = self._wof_system_shades()
        grades = self.film_category_line_ids.filtered('active')
        codes, names = set(grades.mapped('code')), set(grades.mapped('name'))
        return {shade.code for shade in shades if shade.code in codes or shade.value in names}

    def _wof_apply_tint(self, use_all=None, codes=None):
        """Same rules as the film wizard: archive removed grades, never delete."""
        self.ensure_one()
        shades, profile = self._wof_system_shades()
        Grade = self.env['wof.film.category.lines'].with_context(active_test=False)
        existing = Grade.search([('header_id', '=', self.id)])
        if use_all is None:
            use_all = self.use_system_tint_grades
        if use_all:
            wanted = shades
        else:
            if codes is None:
                codes = self._wof_selected_shade_codes(shades)
            wanted = shades.filtered(lambda shade: shade.code in set(codes))
        if not wanted and shades:
            raise ValidationError(_('اختر درجة لون واحدة على الأقل لهذا الفيلم.'))
        wanted_codes = set(wanted.mapped('code'))
        method = profile.tint_numbering_method if profile else 'sequential'
        for shade in wanted:
            grade = existing.filtered(lambda rec: rec.code == shade.code)[:1] or \
                existing.filtered(lambda rec: rec.name == shade.value)[:1]
            vals = {'header_id': self.id, 'sequence': shade.sequence, 'name': shade.value,
                    'code': shade.code, 'active': True}
            if method == 'percentage':
                digits = re.sub(r'[^0-9]', '', shade.value or '')
                if digits:
                    vals['transmission_percent'] = max(0, min(100, int(digits)))
            grade.write(vals) if grade else Grade.create(vals)
        removed = existing.filtered(lambda rec: rec.active and rec.code not in wanted_codes)
        if removed:
            # Component tint policies must not point at an archived grade.
            for line in self.film_part_line_ids:
                vals = {}
                if line.film_category_line_id in removed:
                    vals['film_category_line_id'] = False
                if line.allowed_grade_ids & removed:
                    vals['allowed_grade_ids'] = [(3, grade.id) for grade in line.allowed_grade_ids & removed]
                if vals:
                    line.write(vals)
            removed.write({'active': False})
        self.use_system_tint_grades = bool(use_all)

    def _wof_policies(self, profile):
        system_sizes = self.env['wof.car.size'].search([
            ('company_id', '=', self.company_id.id), ('active', '=', True),
        ])
        system_tax = profile.operation_tax_id if profile else self.env['account.tax']
        return {
            'sizes': {
                'custom': not self.use_system_car_sizes,
                'value': self.car_size_ids.ids if not self.use_system_car_sizes else system_sizes.ids,
                'system': system_sizes.ids,
            },
            'pricing': {
                'custom': not self.use_system_pricing_policy, 'value': self.pricing_policy,
                'system': profile.operation_pricing_policy if profile else 'fixed',
            },
            'tax': {
                'custom': not self.use_system_tax_policy,
                'enabled': self.tax_enabled, 'tax_id': self.tax_id.id or False,
                'system_enabled': profile.operation_tax_enabled if profile else False,
                'system_tax_id': system_tax.id or False,
            },
            'commission': {
                'custom': not self.use_system_commission_policy,
                'event': self.commission_event, 'calc': self.commission_calculation_policy,
                'system_event': profile.commission_event if profile else 'delivery',
                'system_calc': ('by_size' if profile and profile.advanced_commission else 'fixed'),
            },
            'discount': {
                'custom': not self.use_system_discount_policy,
                'enabled': self.discount_enabled, 'limit': self.discount_limit,
                'system_enabled': profile.discount_enabled if profile else False,
                'system_limit': profile.discount_default_limit if profile else 0.0,
            },
        }

    def wof_film_load(self):
        self.ensure_one()
        self._wof_flow_can_read()
        self.check_access_rule('read')
        shades, profile = self._wof_system_shades()
        grades = self.film_category_line_ids.filtered('active').sorted(lambda rec: (rec.sequence, rec.id))
        active_codes = self._wof_selected_shade_codes(shades)
        use_all = self.use_system_tint_grades
        readiness = self._wof_readiness()
        components = []
        for line in self._wof_commercial_lines():
            part = line.car_part_id
            is_area = part.part_type == 'service_area'
            components.append({
                'line_id': line.id, 'part_id': part.id, 'name': part.name, 'code': part.code,
                'type': part.part_type,
                'template': part.default_template_id.name if is_area and part.default_template_id else '',
                'kids': [child.name for child in self._wof_area_parts(part)] if is_area else [],
                'templates': [{
                    'id': template.id, 'name': template.name, 'is_default': template.is_default,
                    'parts': template.component_ids.mapped('name'),
                } for template in part.template_ids.filtered('active').sorted(lambda rec: (rec.sequence, rec.id))] if is_area else [],
                'warning_msg': part.warning_msg or '',
                'default_grade_id': line.film_category_line_id.id or False,
                'allowed_ids': line.allowed_grade_ids.filtered('active').ids,
                'price_ok': readiness['lines'].get(line.id, {}).get('price', False),
                'commission_ok': readiness['lines'].get(line.id, {}).get('commission', False),
            })
        taxes = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'), ('company_id', '=', self.company_id.id), ('active', '=', True),
        ])
        sizes = self.env['wof.car.size'].search([
            ('company_id', '=', self.company_id.id), ('active', '=', True),
        ])
        readiness.pop('lines')
        return {
            'film': {
                'id': self.id, 'name': self.name, 'code': self.code, 'description': self.description or '',
                'item_type': self.item_type, 'active': self.active,
                'warranty_period': self.warranty_period, 'warranty_unit': self.warranty_unit,
                'inventory': self.is_effected_in_inventory, 'product_required': self.car_film_product_required,
                'warning_msg': self.warning_msg or '',
                'activity': {'id': self.service_type_id.id, 'name': self.service_type_id.name,
                             'supports_grades': bool(self.supports_color_grades)},
            },
            'tint': {
                'method': profile.tint_numbering_method if profile else 'sequential',
                'use_all': use_all,
                'shades': [{'code': shade.code, 'value': shade.value,
                            'selected': use_all or shade.code in active_codes}
                           for shade in shades],
            },
            'grades': [{'id': grade.id, 'name': grade.name, 'code': grade.code} for grade in grades],
            'components': components,
            'policies': self._wof_policies(profile),
            'sizes': [{'id': size.id, 'name': size.name} for size in sizes],
            'taxes': [{'id': tax.id, 'name': tax.display_name, 'price_include': bool(tax.price_include)}
                      for tax in taxes],
            'readiness': readiness,
        }

    def wof_film_parts_search(self, query='', part_type=False):
        """Masters that can still be added to this film, optionally of one type."""
        self.ensure_one()
        self._wof_flow_can_read()
        taken = self._wof_commercial_lines().mapped('car_part_id').ids
        domain = [('company_id', '=', self.company_id.id), ('active', '=', True), ('id', 'not in', taken)]
        if part_type in ('car_part', 'service_area'):
            domain.append(('part_type', '=', part_type))
        if (query or '').strip():
            domain += ['|', ('name', 'ilike', query.strip()), ('code', 'ilike', query.strip())]
        parts = self.env['wof.car.parts'].search(domain, order='priority_part, name, id', limit=200)
        result = []
        for part in parts:
            is_area = part.part_type == 'service_area'
            result.append({
                'id': part.id, 'name': part.name, 'code': part.code, 'type': part.part_type,
                'kids': len(self._wof_area_parts(part)) if is_area else 0,
                'templates': len(part.template_ids.filtered('active')) if is_area else 0,
                'usable': (not is_area) or bool(self._wof_area_parts(part)),
            })
        return result

    # ------------------------------------------------------- component master
    def _wof_component_code(self, part_type):
        prefix = 'AREA' if part_type == 'service_area' else 'PART'
        Master = self.env['wof.car.parts'].with_context(active_test=False)
        number = Master.search_count([('company_id', '=', self.company_id.id), ('part_type', '=', part_type)]) + 1
        for _attempt in range(10000):
            code = '%s-%04d' % (prefix, number)
            if not Master.search_count([('company_id', '=', self.company_id.id), ('code', '=', code)]):
                return code
            number += 1
        raise ValidationError(_('تعذر إنشاء كود تلقائي فريد للمكوّن. أدخل الكود يدويًا.'))

    def wof_component_load(self, part_id=False):
        """Data for the component form: the master (when editing) and the choices."""
        self.ensure_one()
        self._wof_flow_can_read()
        company = self.company_id
        part = self.env['wof.car.parts'].browse(int(part_id or 0)).exists()
        if part and part.company_id != company:
            raise AccessError(_('المكوّن غير متاح لهذه الشركة.'))
        if part and part.part_type == 'service_area':
            part.ensure_service_area_templates()
        uses = 0
        if part:
            uses = self.env['wof.film.parts.lines'].search_count([
                ('car_part_id', '=', part.id), ('part_selected', '=', True), ('header_id', '!=', self.id),
            ])
        car_parts = self.env['wof.car.parts'].search([
            ('company_id', '=', company.id), ('part_type', '=', 'car_part'), ('active', '=', True),
        ], order='priority_part, name, id')
        options = self.env['wof.car.part.options'].search([('active', '=', True)], order='name')
        return {
            'part': {
                'id': part.id, 'name': part.name, 'code': part.code, 'type': part.part_type,
                'product': {'id': part.product_id.id, 'name': part.product_id.display_name} if part.product_id else False,
                'priority': part.priority_part, 'options_required': part.part_options_required,
                'option_ids': part.part_options_ids.ids, 'notes': part.notes or '',
                'warning_msg': part.warning_msg or '',
                'templates': [{
                    'id': template.id, 'name': template.name, 'is_default': template.is_default,
                    'component_ids': template.component_ids.ids,
                } for template in part.template_ids.filtered('active').sorted(lambda rec: (rec.sequence, rec.id))],
                'other_films': uses,
            } if part else False,
            'car_parts': [{'id': rec.id, 'name': rec.name, 'code': rec.code} for rec in car_parts if rec != part],
            'options': [{'id': rec.id, 'name': rec.name} for rec in options],
        }

    def wof_service_products(self, query=''):
        self.ensure_one()
        self._wof_flow_can_read()
        domain = [('type', '=', 'service'), ('company_id', 'in', [False, self.company_id.id])]
        if (query or '').strip():
            domain.append(('name', 'ilike', query.strip()))
        products = self.env['product.product'].search(domain, limit=20, order='name')
        return [{'id': product.id, 'name': product.display_name} for product in products]

    def _wof_validate_templates(self, templates, company):
        if not templates:
            raise ValidationError(_('أضف نموذج مكونات واحدًا على الأقل لمنطقة الخدمة.'))
        names = []
        Part = self.env['wof.car.parts']
        for template in templates:
            name = (template.get('name') or '').strip()
            if not name:
                raise ValidationError(_('أدخل اسمًا لكل نموذج مكونات.'))
            names.append(name.lower())
            parts = Part.browse([int(i) for i in template.get('component_ids') or []]).exists()
            if not parts:
                raise ValidationError(_('كل نموذج يجب أن يحتوي على مكوّن واحد على الأقل.'))
            if parts.filtered(lambda rec: rec.company_id != company or rec.part_type != 'car_part'):
                raise ValidationError(_('مكونات النماذج يجب أن تكون أجزاء سيارة من نفس الشركة.'))
            template['_parts'] = parts
            template['name'] = name
        if len(names) != len(set(names)):
            raise ValidationError(_('لا يمكن تكرار اسم النموذج داخل منطقة الخدمة.'))
        if len([t for t in templates if t.get('is_default')]) != 1:
            raise ValidationError(_('حدد نموذجًا افتراضيًا واحدًا فقط لمنطقة الخدمة.'))

    def _wof_sync_templates(self, part, templates):
        """Same rules as the develop dialog: update, create, archive missing; one default."""
        Template = self.env['wof.service.area.template'].with_context(active_test=False)
        existing = {template.id: template for template in part.template_ids}
        keep = []
        default_parts = self.env['wof.car.parts']
        # Clear the old default first and write the new default first, so the
        # "single default template" constraint never sees two defaults.
        part.template_ids.filtered('is_default').with_context(skip_default_sync=True).write({'is_default': False})
        ordered = sorted(enumerate(templates, start=1), key=lambda item: not item[1].get('is_default'))
        for sequence, template in ordered:
            vals = {
                'name': template['name'], 'sequence': sequence * 10, 'service_area_id': part.id,
                'component_ids': [(6, 0, template['_parts'].ids)], 'active': True,
                'is_default': bool(template.get('is_default')),
            }
            record = existing.get(int(template.get('id') or 0))
            if record:
                record.with_context(skip_default_sync=True).write(vals)
            else:
                record = Template.with_context(skip_default_sync=True).create(vals)
            keep.append(record.id)
            if template.get('is_default'):
                default_parts = template['_parts']
        obsolete = Template.search([('service_area_id', '=', part.id), ('id', 'not in', keep), ('active', '=', True)])
        if obsolete:
            obsolete.with_context(skip_default_sync=True).write({'active': False, 'is_default': False})
        part.service_area_part_ids = [(6, 0, default_parts.ids)]

    def wof_component_save(self, payload):
        """Create (and add to this film) or edit a component master."""
        self.ensure_one()
        self._wof_flow_can_read()
        self._wof_matrix_check_access()
        company = self.company_id
        Master = self.env['wof.car.parts'].with_context(active_test=False)
        part = Master.browse(int(payload.get('id') or 0)).exists()
        if part and part.company_id != company:
            raise AccessError(_('المكوّن غير متاح لهذه الشركة.'))
        part_type = part.part_type if part else payload.get('type')
        if part_type not in ('car_part', 'service_area'):
            raise ValidationError(_('نوع المكوّن غير صحيح.'))
        name = (payload.get('name') or '').strip()
        if not name:
            raise ValidationError(_('أدخل اسم المكوّن أولاً.'))
        duplicate = Master.search([('company_id', '=', company.id), ('name', '=ilike', name), ('id', '!=', part.id or 0)], limit=1)
        if duplicate:
            raise ValidationError(_('يوجد مكوّن باسم "%s" بالفعل. أضفه من القائمة بدل إنشاء نسخة مكررة.') % duplicate.display_name)
        code = (payload.get('code') or '').strip() or (part.code if part else '') or self._wof_component_code(part_type)
        if Master.search_count([('company_id', '=', company.id), ('code', '=', code), ('id', '!=', part.id or 0)]):
            raise ValidationError(_('كود المكوّن "%s" مستخدم مسبقًا في هذه الشركة.') % code)
        if payload.get('auto_product'):
            product = self.env['product.product'].create({
                'name': name, 'type': 'service', 'sale_ok': True, 'purchase_ok': False,
            })
        else:
            product = self.env['product.product'].browse(int(payload.get('product_id') or 0)).exists()
            if not product:
                raise ValidationError(_('اختر الصنف الخدمي المرتبط بالمكوّن، أو فعّل الإنشاء التلقائي.'))
            if product.type != 'service':
                raise ValidationError(_('الصنف المرتبط بالمكوّن يجب أن يكون من نوع خدمة.'))
        templates = payload.get('templates') or []
        if part_type == 'service_area':
            self._wof_validate_templates(templates, company)
        try:
            priority = int(payload.get('priority') or 0)
        except (TypeError, ValueError):
            raise ValidationError(_('ترتيب الأولوية يجب أن يكون رقمًا.'))
        options = self.env['wof.car.part.options'].browse([int(i) for i in payload.get('option_ids') or []]).exists()
        vals = {
            'name': name, 'code': code, 'product_id': product.id, 'priority_part': priority,
            'part_options_required': bool(payload.get('options_required')) and bool(options),
            'part_options_ids': [(6, 0, options.ids)],
            'notes': (payload.get('notes') or '').strip() or False,
            'warning_msg': (payload.get('warning_msg') or '').strip() or False,
        }
        if part:
            part.write(vals)
        else:
            vals.update({'part_type': part_type, 'company_id': company.id, 'active': True})
            if part_type == 'service_area':
                vals['service_area_part_ids'] = [(6, 0, [t for t in templates if t.get('is_default')][0]['_parts'].ids)]
            part = Master.create(vals)
        if part_type == 'service_area':
            self._wof_sync_templates(part, templates)
        if not payload.get('id'):
            self._wof_op_comp_add({'part_id': part.id})
        if part_type == 'car_part' and self.supports_color_grades and self.item_type == 'film' and 'tint' in payload:
            line = self._wof_commercial_lines().filtered(lambda rec: rec.car_part_id == part)
            if line:
                self._wof_op_comp_tint(dict(payload['tint'], line_id=line.id))
        return self.wof_film_load()

    def wof_film_apply(self, op, payload=None):
        self.ensure_one()
        self._wof_flow_can_read()
        self._wof_matrix_check_access()
        payload = payload or {}
        handler = {
            'basic': self._wof_op_basic,
            'tint': self._wof_op_tint,
            'comp_add': self._wof_op_comp_add,
            'comp_add_many': self._wof_op_comp_add_many,
            'comp_remove': self._wof_op_comp_remove,
            'comp_move': self._wof_op_comp_move,
            'comp_reorder': self._wof_op_comp_reorder,
            'comp_tint': self._wof_op_comp_tint,
            'policy': self._wof_op_policy,
            'activate': self._wof_op_activate,
            'deactivate': self._wof_op_deactivate,
        }.get(op)
        if not handler:
            raise ValidationError(_('عملية غير معروفة في محرر الفيلم.'))
        handler(payload)
        return self.wof_film_load()

    def _wof_op_basic(self, payload):
        vals = {key: value for key, value in payload.items() if key in BASIC_FIELDS}
        if set(payload) - BASIC_FIELDS:
            raise ValidationError(_('لا يمكن تعديل هذا الحقل من المحرر.'))
        if 'name' in vals:
            vals['name'] = (vals['name'] or '').strip()
            if not vals['name']:
                raise ValidationError(_('أدخل اسم الفيلم أو الخدمة.'))
        if 'code' in vals:
            code = re.sub(r'[^A-Z0-9_.-]+', '-', (vals['code'] or '').strip().upper()).strip('-')
            vals['code'] = code or self._wof_new_code(vals.get('name') or self.name, self.company_id)
        if 'item_type' in vals:
            if vals['item_type'] not in ('film', 'service'):
                raise ValidationError(_('نوع العنصر غير صحيح.'))
            if vals['item_type'] == 'service':
                vals['car_film_product_required'] = False
        if 'warranty_period' in vals:
            try:
                vals['warranty_period'] = int(vals['warranty_period'] or 0)
            except (TypeError, ValueError):
                raise ValidationError(_('مدة الضمان يجب أن تكون رقمًا.'))
            if vals['warranty_period'] < 0:
                raise ValidationError(_('مدة الضمان لا يمكن أن تكون سالبة.'))
        if 'warranty_unit' in vals and vals['warranty_unit'] not in dict(WARRANTY_UNITS):
            raise ValidationError(_('وحدة الضمان غير صحيحة.'))
        if vals.get('is_effected_in_inventory') is False:
            vals['car_film_product_required'] = False
        for key in ('is_effected_in_inventory', 'car_film_product_required'):
            if key in vals:
                vals[key] = bool(vals[key])
        if 'warning_msg' in vals:
            vals['warning_msg'] = (vals['warning_msg'] or '').strip() or False
        self.write(vals)
        if vals.get('item_type') == 'film' and self.supports_color_grades and not self.film_category_line_ids.filtered('active'):
            self._wof_apply_tint(use_all=True)

    def _wof_op_tint(self, payload):
        if not (self.supports_color_grades and self.item_type == 'film'):
            raise ValidationError(_('درجات اللون متاحة لأفلام العزل الحراري فقط.'))
        if payload.get('use_all'):
            self._wof_apply_tint(use_all=True)
            return
        shades, _profile = self._wof_system_shades()
        # Switching from "all" starts the specific selection from everything the
        # film offers today; if nothing matches yet, start from all system shades.
        codes = self._wof_selected_shade_codes(shades)
        if self.use_system_tint_grades or not codes:
            codes = set(shades.mapped('code'))
        if 'code' in payload:
            if payload.get('selected'):
                codes.add(payload['code'])
            else:
                codes.discard(payload['code'])
        self._wof_apply_tint(use_all=False, codes=codes)

    def _wof_op_comp_add(self, payload):
        part = self.env['wof.car.parts'].browse(int(payload.get('part_id') or 0)).exists()
        if not part or part.company_id != self.company_id or not part.active:
            raise ValidationError(_('المكوّن المحدد غير متاح لهذه الشركة.'))
        if part.part_type == 'service_area' and not self._wof_area_parts(part):
            raise ValidationError(_('منطقة الخدمة يجب أن تحتوي على جزء واحد على الأقل قبل استخدامها.'))
        line = self.film_part_line_ids.filtered(lambda rec: rec.car_part_id == part)[:1]
        sequence = max(self._wof_commercial_lines().mapped('sequence') or [0]) + 10
        if line:
            line.write({'part_selected': True, 'sequence': sequence})
        else:
            self.env['wof.film.parts.lines'].create({
                'header_id': self.id, 'car_part_id': part.id, 'part_selected': True, 'sequence': sequence,
            })

    def _wof_op_comp_add_many(self, payload):
        parts = self.env['wof.car.parts'].browse([int(i) for i in payload.get('part_ids') or []]).exists()
        if not parts:
            raise ValidationError(_('حدد مكوّنًا واحدًا على الأقل قبل الإضافة.'))
        empty = parts.filtered(lambda part: part.part_type == 'service_area' and not self._wof_area_parts(part))
        if empty:
            raise ValidationError(_('مناطق الخدمة التالية لا تحتوي على نماذج أو أجزاء: %s') % '، '.join(empty.mapped('name')))
        taken = self._wof_commercial_lines().mapped('car_part_id')
        to_add = (parts - taken).sorted(lambda rec: (rec.priority_part, rec.name or '', rec.id))
        if not to_add:
            raise ValidationError(_('جميع المكونات المحددة مضافة بالفعل لهذا الفيلم / الخدمة.'))
        for part in to_add:
            self._wof_op_comp_add({'part_id': part.id})

    def _wof_comp_line(self, payload):
        line = self._wof_commercial_lines().filtered(lambda rec: rec.id == payload.get('line_id'))
        if not line:
            raise ValidationError(_('المكوّن غير موجود في هذا الفيلم.'))
        return line

    def _wof_op_comp_remove(self, payload):
        # Keep the line (and its history) but take it out of the film.
        self._wof_comp_line(payload).write({'part_selected': False})

    def _wof_op_comp_move(self, payload):
        line = self._wof_comp_line(payload)
        lines = list(self._wof_commercial_lines())
        index = lines.index(line)
        target = index + (-1 if payload.get('direction') == 'up' else 1)
        if 0 <= target < len(lines):
            lines[index], lines[target] = lines[target], lines[index]
            for position, record in enumerate(lines, start=1):
                if record.sequence != position * 10:
                    record.sequence = position * 10

    def _wof_op_comp_reorder(self, payload):
        """Drag-and-drop order: ``line_ids`` lists the film's components top to bottom."""
        lines = self._wof_commercial_lines()
        order = [int(i) for i in payload.get('line_ids') or []]
        if sorted(order) != sorted(lines.ids):
            raise ValidationError(_('ترتيب المكوّنات لا يطابق مكوّنات الفيلم. أعد فتح المحرر.'))
        by_id = {line.id: line for line in lines}
        for position, line_id in enumerate(order, start=1):
            if by_id[line_id].sequence != position * 10:
                by_id[line_id].sequence = position * 10

    def _wof_op_comp_tint(self, payload):
        line = self._wof_comp_line(payload)
        grades = self.film_category_line_ids.filtered('active')
        allowed = grades.filtered(lambda grade: grade.id in set(payload.get('allowed_ids') or []))
        default = grades.filtered(lambda grade: grade.id == payload.get('default_grade_id'))
        if allowed and default and default not in allowed:
            allowed |= default
        line.write({'film_category_line_id': default.id or False, 'allowed_grade_ids': [(6, 0, allowed.ids)]})

    def _wof_op_policy(self, payload):
        key = payload.get('key')
        custom = bool(payload.get('custom'))
        profile = self._wof_profile(self.company_id)
        system = self._wof_system_policy_vals(profile) if profile else {}
        if key == 'sizes':
            if custom:
                sizes = self.env['wof.car.size'].search([
                    ('company_id', '=', self.company_id.id), ('active', '=', True),
                    ('id', 'in', [int(i) for i in payload.get('size_ids') or []]),
                ])
                if not sizes:
                    raise ValidationError(_('اختر حجم سيارة واحدًا على الأقل.'))
                self.write({'use_system_car_sizes': False, 'car_size_ids': [(6, 0, sizes.ids)]})
            else:
                self.write({'use_system_car_sizes': True, 'car_size_ids': system.get('car_size_ids', [(5, 0, 0)])})
        elif key == 'pricing':
            if custom:
                value = payload.get('value')
                if value not in ('fixed', 'by_size'):
                    raise ValidationError(_('سياسة التسعير غير صحيحة.'))
                self.write({'use_system_pricing_policy': False, 'pricing_policy': value})
            else:
                self.write({'use_system_pricing_policy': True, 'pricing_policy': system.get('pricing_policy', 'fixed')})
        elif key == 'tax':
            if custom:
                enabled = bool(payload.get('enabled'))
                tax = self.env['account.tax']
                if enabled:
                    tax = tax.search([
                        ('id', '=', int(payload.get('tax_id') or 0)), ('type_tax_use', '=', 'sale'),
                        ('company_id', '=', self.company_id.id),
                    ])
                    if not tax:
                        raise ValidationError(_('اختر الضريبة، أو أوقف تطبيق الضريبة لهذا الفيلم.'))
                self.write({
                    'use_system_tax_policy': False, 'tax_enabled': enabled, 'tax_id': tax.id or False,
                    'price_input_mode': 'included' if tax and tax.price_include else 'excluded',
                })
            else:
                self.write({key_: system[key_] for key_ in ('use_system_tax_policy', 'tax_enabled', 'tax_id', 'price_input_mode') if key_ in system})
        elif key == 'commission':
            if custom:
                event, calc = payload.get('event'), payload.get('calc')
                if event not in ('delivery', 'invoice') or calc not in ('fixed', 'by_size'):
                    raise ValidationError(_('سياسة العمولة غير صحيحة.'))
                self.write({'use_system_commission_policy': False, 'commission_event': event,
                            'commission_calculation_policy': calc})
            else:
                self.write({key_: system[key_] for key_ in ('use_system_commission_policy', 'commission_event', 'commission_calculation_policy') if key_ in system})
        elif key == 'discount':
            if custom:
                enabled = bool(payload.get('enabled'))
                try:
                    limit = float(payload.get('limit') or 0.0)
                except (TypeError, ValueError):
                    raise ValidationError(_('حد الخصم يجب أن يكون رقمًا.'))
                if limit < 0 or limit > 100:
                    raise ValidationError(_('حد الخصم يجب أن يكون بين 0 و100.'))
                self.write({'use_system_discount_policy': False, 'discount_enabled': enabled,
                            'discount_limit': limit if enabled else 0.0})
            else:
                self.write({key_: system[key_] for key_ in ('use_system_discount_policy', 'discount_enabled', 'discount_limit') if key_ in system})
        else:
            raise ValidationError(_('سياسة غير معروفة.'))

    def _wof_op_activate(self, payload):
        readiness = self._wof_readiness()
        if not readiness['ready']:
            names = {'components': _('المكوّنات'), 'tint': _('درجات اللون'), 'prices': _('الأسعار')}
            raise ValidationError(_('لا يمكن التفعيل الآن، ينقص: %s') % '، '.join(names[key] for key in readiness['missing']))
        self.write({'active': True})

    def _wof_op_deactivate(self, payload):
        self.write({'active': False})

    # ---------------------------------------------------------------- actions
    def _wof_editor_action(self, step=None):
        self.ensure_one()
        return {
            'type': 'ir.actions.client', 'tag': 'wof_film_editor', 'name': self.name,
            'target': 'new', 'params': {'film_id': self.id, 'step': step or False},
            'context': {'dialog_size': 'extra-large'},
        }

    def action_configure(self):
        """The guided editor replaces the old film setup wizard everywhere."""
        self.ensure_one()
        return self._wof_editor_action()

    @api.model
    def action_open_films_hub(self):
        return {'type': 'ir.actions.client', 'tag': 'wof_films_hub', 'name': _('الأفلام والخدمات'), 'target': 'current'}
