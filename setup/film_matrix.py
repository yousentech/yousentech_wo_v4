# -*- coding: utf-8 -*-
"""Pricing & commission matrix service for a film / service.

The OWL client action ``wof_pricing_matrix`` reads one JSON snapshot with
``wof_matrix_load`` and writes the whole edited state back with
``wof_matrix_save``.  The persistent data contract is unchanged:

* price lines: one general line (no size) when the film pricing policy is
  ``fixed``; one line per configured car size when it is ``by_size``.  The
  UI modes "same price for all sizes" and "free for all sizes" are only
  presentations of the per-size lines, exactly like the existing dialog.
* commission lines: one general line when the component policy is ``fixed``;
  one line per size when ``by_size``.  A service area whose commission source
  is ``from_parts`` gets derived lines (sum of the parts of its default
  template); each part of each of its templates has its own setting in
  ``wof.film.area.part.commission`` (see setup/area_part_commission.py),
  independent from the part sold alone.
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class WofFilmMatrix(models.Model):
    _inherit = 'wof.film.category'

    # ------------------------------------------------------------------ helpers
    def _wof_matrix_check_access(self):
        self.ensure_one()
        self.check_access_rights('write')
        self.check_access_rule('write')

    def _wof_matrix_sizes(self):
        self.ensure_one()
        sizes = self.car_size_ids.filtered('active')
        if not sizes:
            sizes = self.env['wof.car.size'].search([
                ('active', '=', True),
            ], order='name')
        return sizes.sorted(lambda size: (getattr(size, 'sequence', 0) or 0, size.id))

    @api.model
    def _wof_area_parts(self, area):
        """Parts of a service area: its default template, else the legacy list."""
        if not area or area.part_type != 'service_area':
            return self.env['wof.car.parts']
        template = area.default_template_id
        if template and template.component_ids:
            return template.component_ids
        return area.service_area_part_ids

    def _wof_commercial_lines(self):
        self.ensure_one()
        return self.film_part_line_ids.filtered('part_selected').sorted(
            lambda line: (line.sequence, line.id)
        )

    def _wof_tax(self):
        self.ensure_one()
        if self.tax_enabled and self.tax_id:
            return self.tax_id
        return self.env['account.tax']

    @api.model
    def _wof_num(self, value):
        if value in (None, False, ''):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValidationError(_('قيمة غير صالحة: %s') % value)
        if number < 0:
            raise ValidationError(_('القيم لا يمكن أن تكون سالبة.'))
        return number

    @api.model
    def _wof_line_by_size(self, lines):
        result = {}
        for line in lines:
            result[line.car_size_id.id if line.car_size_id else 0] = line
        return result

    # --------------------------------------------------------------- snapshot
    def _wof_price_snapshot(self, part_line, sizes, policy):
        by_size = self._wof_line_by_size(part_line.price_line_ids)
        general = by_size.get(0)

        def cell(line):
            if not line:
                return {'amount': None, 'free': False, 'readonly': False}
            return {
                'amount': 0.0 if line.free_part else line.part_price,
                'free': bool(line.free_part),
                'readonly': bool(line.price_readonly) and not line.free_part,
            }

        # Only the lines of the active policy are shown: leftovers of the other
        # policy (older data) must not resurface when the user switches modes.
        if policy == 'by_size':
            cells = {str(size.id): cell(by_size.get(size.id)) for size in sizes}
            values = list(cells.values())
            if values and all(value['free'] for value in values):
                mode = 'free'
                general_cell = {'amount': 0.0, 'free': True, 'readonly': False}
            elif values and all(value['amount'] is not None and not value['free'] for value in values) and len(
                {(value['amount'], value['readonly']) for value in values}
            ) == 1:
                # "Same price for all sizes" is stored per size: show it as the shared value.
                mode = 'uniform'
                general_cell = dict(values[0])
            else:
                mode = 'size'
                general_cell = cell(False)
        else:
            cells = {str(size.id): cell(False) for size in sizes}
            mode = 'free' if general and general.free_part else 'uniform'
            general_cell = cell(general)
        return {'mode': mode, 'general': general_cell, 'sizes': cells}

    def _wof_commission_snapshot(self, part_line, sizes):
        by_size = self._wof_line_by_size(part_line.commission_line_ids)
        general = by_size.get(0)
        policy = part_line.commission_calculation_policy or self.commission_calculation_policy or 'fixed'
        by_size_policy = policy == 'by_size'
        return {
            'source': (
                part_line.service_commission_source
                if part_line.part_type == 'service_area' else 'independent'
            ),
            'type': part_line.commission_value_type or 'fixed',
            'policy': policy,
            'general': general.commission if general and not by_size_policy else None,
            'sizes': {
                str(size.id): (
                    by_size[size.id].commission if by_size_policy and size.id in by_size else None
                )
                for size in sizes
            },
            'readonly': bool(part_line.commission_readonly),
            'distribution': part_line.technician_commission_distribution or 'equal',
        }

    def _wof_area_templates_snapshot(self, area_line, sizes):
        """Templates of an area, each with its parts' commission setting inside the area."""
        result = []
        for template in self._wof_area_templates(area_line.car_part_id):
            parts = []
            for part in template.component_ids:
                config = self._wof_area_config(area_line, template, part)
                standalone = self._wof_standalone_line(part)
                method = config.method if config else ('part' if standalone else 'fixed')
                if method == 'part' and not standalone:
                    method = 'fixed'
                general = config.value_ids.filtered(lambda rec: not rec.car_size_id)[:1] if config else None
                by_size = {rec.car_size_id.id: rec.amount for rec in config.value_ids if rec.car_size_id} \
                    if config else {}
                standalone_desc = ''
                if standalone:
                    if standalone.commission_value_type == 'percent':
                        standalone_desc = _('نسبة من سعر الجزء المستقل')
                    else:
                        standalone_desc = _('مبلغ الجزء المستقل')
                rule = config.distribution if config else ('part' if standalone else 'equal')
                if rule == 'part' and not standalone:
                    rule = 'equal'
                standalone_rule = (standalone.technician_commission_distribution
                                   if standalone and standalone.technician_commission_distribution in
                                   ('equal', 'by_technician_ratio') else 'equal')
                parts.append({
                    'part_id': part.id,
                    'name': part.name,
                    'code': part.code,
                    'standalone': bool(standalone),
                    'standalone_desc': standalone_desc,
                    'standalone_rule': standalone_rule,
                    'resolved': {
                        str(size.id): self._wof_line_commission_amount(standalone, size) if standalone else None
                        for size in sizes
                    },
                    'resolved_general': self._wof_line_commission_amount(standalone, False) if standalone else None,
                    'commission': {
                        'method': method,
                        'general': general.amount if general else None,
                        'sizes': {str(size.id): by_size.get(size.id) for size in sizes},
                        'distribution': rule,
                    },
                })
            result.append({
                'id': template.id, 'name': template.name, 'is_default': template.is_default, 'parts': parts,
            })
        return result

    def wof_matrix_load(self):
        """Return the full matrix snapshot for the OWL client action."""
        self.ensure_one()
        self._wof_matrix_check_access()
        sizes = self._wof_matrix_sizes()
        policy = self.pricing_policy or 'fixed'
        tax = self._wof_tax()
        all_lines = self.film_part_line_ids
        lines = []
        for part_line in self._wof_commercial_lines():
            part = part_line.car_part_id
            is_area = part.part_type == 'service_area'
            templates = []
            template_name = ''
            if is_area:
                template = part.default_template_id
                template_name = template.name if template else ''
                templates = self._wof_area_templates_snapshot(part_line, sizes)
            lines.append({
                'id': part_line.id,
                'part_id': part.id,
                'name': part.name,
                'code': part.code,
                'type': part.part_type,
                'template_name': template_name,
                'templates': templates,
                'price': self._wof_price_snapshot(part_line, sizes, policy),
                'discount_policy': part_line.discount_policy,
                'discount_limit': part_line.discount_limit,
                'commission': self._wof_commission_snapshot(part_line, sizes),
            })
        return {
            'film': {
                'id': self.id,
                'name': self.display_name,
                'code': self.code,
                'activity': self.service_type_id.display_name,
                'activity_type': self.service_type_id.service_options or 'others',
                'pricing_policy': policy,
                'commission_policy': self.commission_calculation_policy or 'fixed',
                'commission_event': self.commission_event,
                'tax_rate': (tax.amount / 100.0) if tax and tax.amount_type == 'percent' else 0.0,
                'tax_name': tax.name if tax else '',
                'price_included': (self.price_input_mode == 'included') or bool(tax and tax.price_include),
                'currency': self.env.company.currency_id.symbol or '',
            },
            'sizes': [{'id': size.id, 'name': size.name, 'code': size.code} for size in sizes],
            'lines': lines,
        }

    # ------------------------------------------------------------------- save
    def _wof_upsert(self, model, part_line, existing, desired):
        """``desired`` maps size id (0 = general) to a vals dict."""
        by_size = self._wof_line_by_size(existing)
        obsolete = existing.filtered(
            lambda line: (line.car_size_id.id if line.car_size_id else 0) not in desired
        )
        if obsolete:
            obsolete.unlink()
        for size_id, vals in desired.items():
            payload = dict(vals, part_line_id=part_line.id, car_size_id=size_id or False)
            target = by_size.get(size_id)
            if target and target.exists():
                target.write(payload)
            else:
                model.create(payload)

    def _wof_save_price(self, part_line, data, sizes, policy, tax):
        mode = data.get('mode') or 'size'
        Price = self.env['wof.film.parts.price.lines']

        def vals_for(cell, force_free=False, force_amount=None, force_readonly=None):
            free = force_free or bool(cell.get('free'))
            amount = force_amount if force_amount is not None else self._wof_num(cell.get('amount'))
            if not free and amount is None:
                return None
            readonly = force_readonly if force_readonly is not None else bool(cell.get('readonly'))
            return {
                'part_price': 0.0 if free else amount,
                'free_part': free,
                'price_readonly': False if free else readonly,
                'tax_id': False if free else (tax.id if tax else False),
            }

        desired = {}
        general = data.get('general') or {}
        if policy == 'by_size':
            cells = data.get('sizes') or {}
            for size in sizes:
                cell = cells.get(str(size.id)) or {}
                if mode == 'free':
                    vals = vals_for(cell, force_free=True)
                elif mode == 'uniform':
                    amount = self._wof_num(general.get('amount'))
                    vals = None if amount is None else vals_for(
                        {}, force_amount=amount, force_readonly=bool(general.get('readonly'))
                    )
                else:
                    vals = vals_for(cell)
                if vals:
                    desired[size.id] = vals
        else:
            vals = vals_for(general, force_free=(mode == 'free'))
            if vals:
                desired[0] = vals
        self._wof_upsert(Price, part_line, part_line.price_line_ids, desired)
        discount_policy = data.get('discount_policy')
        if discount_policy in ('inherit', 'allow', 'deny'):
            limit = self._wof_num(data.get('discount_limit')) or 0.0
            if limit > 100:
                raise ValidationError(_('حد خصم المكوّن يجب أن يكون بين 0 و100.'))
            part_line.write({
                'discount_policy': discount_policy,
                'discount_limit': limit if discount_policy == 'allow' else 0.0,
            })

    def _wof_save_commission(self, part_line, data, sizes, is_area=False):
        Commission = self.env['wof.film.parts.commission.lines']
        source = data.get('source') if is_area else 'independent'
        value_type = data.get('type') if data.get('type') in ('fixed', 'percent') else 'fixed'
        policy = data.get('policy') if data.get('policy') in ('fixed', 'by_size') else 'fixed'
        distribution = data.get('distribution') or ('by_part' if source == 'from_parts' else 'equal')
        if is_area and source == 'from_parts' and part_line.service_commission_source != 'from_parts' \
                and distribution == 'equal':
            distribution = 'by_part'  # switching to «من الأجزاء»: each part keeps its own split by default
        # «كل جزء حسب تهيئته» exists for service areas only; a part (also a basis
        # part of an area) splits equally or by technician ratio.
        allowed = ('equal', 'by_technician_ratio', 'by_part') if is_area else ('equal', 'by_technician_ratio')
        if distribution not in allowed:
            distribution = 'equal'
        vals = {
            'commission_value_type': value_type,
            'commission_calculation_policy': policy,
            'commission_readonly': bool(data.get('readonly')),
            'technician_commission_distribution': distribution,
        }
        if is_area:
            vals['service_commission_source'] = source if source in ('independent', 'from_parts') else 'independent'
        part_line.write(vals)
        if source == 'from_parts':
            return  # derived after the parts are saved
        values = []
        if policy == 'by_size':
            cells = data.get('sizes') or {}
            desired = {}
            for size in sizes:
                amount = self._wof_num(cells.get(str(size.id)))
                if amount is not None:
                    desired[size.id] = {'commission': amount}
                    values.append(amount)
        else:
            amount = self._wof_num(data.get('general'))
            desired = {0: {'commission': amount}} if amount is not None else {}
            if amount is not None:
                values.append(amount)
        if value_type == 'percent' and any(value > 100 for value in values):
            raise ValidationError(_('نسبة العمولة يجب أن تكون بين 0 و100.'))
        self._wof_upsert(Commission, part_line, part_line.commission_line_ids, desired)

    def _wof_sync_area_commission(self, area_line, sizes):
        """Derive the area's commission lines from its default template parts (shown and
        used as the reference; an order uses the template it chose)."""
        template = area_line.car_part_id.default_template_id or self._wof_area_templates(area_line.car_part_id)[:1]
        Commission = self.env['wof.film.parts.commission.lines']
        if not template:
            self._wof_upsert(Commission, area_line, area_line.commission_line_ids, {})
            return False
        desired = {}
        for size in sizes:
            total = self._wof_area_total(area_line, template, size)
            if total is not None:
                desired[size.id] = {'commission': total}
        values = {vals['commission'] for vals in desired.values()}
        if len(desired) == len(sizes) and len(values) == 1:
            desired = {0: {'commission': values.pop()}}
            policy = 'fixed'
        else:
            policy = 'by_size'
        self._wof_upsert(Commission, area_line, area_line.commission_line_ids, desired)
        area_line.write({'commission_calculation_policy': policy, 'commission_value_type': 'fixed'})
        return bool(desired)

    def _wof_save_area_parts(self, area_line, templates, sizes):
        """Store the parts' commission inside the area, per template."""
        Config = self.env['wof.film.area.part.commission']
        allowed = {template.id: template for template in self._wof_area_templates(area_line.car_part_id)}
        for item in templates or []:
            template = allowed.get(item.get('id'))
            if not template:
                raise ValidationError(_('النموذج لا يتبع منطقة الخدمة «%s».') % area_line.car_part_id.name)
            for index, data in enumerate(item.get('parts') or [], start=1):
                part = template.component_ids.filtered(lambda rec: rec.id == data.get('part_id'))
                if not part:
                    raise ValidationError(_('الجزء لا يتبع النموذج «%s».') % template.name)
                comm = data.get('commission') or {}
                standalone = self._wof_standalone_line(part)
                method = comm.get('method') if comm.get('method') in ('part', 'fixed', 'by_size') else 'fixed'
                if method == 'part' and not standalone:
                    raise ValidationError(_(
                        'الجزء «%s» لا يُباع مستقلًا في هذا الفيلم، فلا يمكن أن تكون عمولته «حسب تهيئة الجزء». '
                        'أدخل عمولته داخل المنطقة.') % part.name)
                rule = comm.get('distribution') if comm.get('distribution') in ('part', 'equal', 'by_technician_ratio') \
                    else 'equal'
                if rule == 'part' and not standalone:
                    rule = 'equal'
                config = self._wof_area_config(area_line, template, part) or Config.create({
                    'area_line_id': area_line.id, 'template_id': template.id, 'part_id': part.id,
                })
                desired = {}
                if method == 'by_size':
                    cells = comm.get('sizes') or {}
                    for size in sizes:
                        amount = self._wof_num(cells.get(str(size.id)))
                        if amount is not None:
                            desired[size.id] = amount
                elif method == 'fixed':
                    amount = self._wof_num(comm.get('general'))
                    if amount is not None:
                        desired[0] = amount
                config.write({'method': method, 'distribution': rule, 'sequence': index})
                existing = {rec.car_size_id.id or 0: rec for rec in config.value_ids}
                for key, rec in existing.items():
                    if key not in desired:
                        rec.unlink()
                for key, amount in desired.items():
                    if key in existing:
                        if existing[key].amount != amount:
                            existing[key].amount = amount
                    else:
                        config.value_ids.create({'config_id': config.id, 'car_size_id': key or False, 'amount': amount})

    def wof_matrix_save(self, payload):
        """Persist the matrix state. Returns a fresh snapshot."""
        self.ensure_one()
        self._wof_matrix_check_access()
        payload = payload or {}
        policy = payload.get('pricing_policy')
        if policy in ('fixed', 'by_size') and policy != self.pricing_policy:
            self.write({'pricing_policy': policy, 'use_system_pricing_policy': False})
        policy = self.pricing_policy or 'fixed'
        sizes = self._wof_matrix_sizes()
        if policy == 'by_size' and not sizes:
            raise ValidationError(_('حدد حجم سيارة واحدًا على الأقل عند استخدام التسعير حسب الحجم.'))
        tax = self._wof_tax()
        commercial = self._wof_commercial_lines()
        by_id = {line.id: line for line in commercial}
        areas_from_parts = self.env['wof.film.parts.lines']
        for item in payload.get('lines') or []:
            part_line = by_id.get(item.get('id'))
            if not part_line:
                raise ValidationError(_('المكوّن لا يتبع هذا الفيلم / الخدمة.'))
            is_area = part_line.part_type == 'service_area'
            price = dict(item.get('price') or {})
            price.update({
                'discount_policy': item.get('discount_policy'),
                'discount_limit': item.get('discount_limit'),
            })
            self._wof_save_price(part_line, price, sizes, policy, tax)
            commission = item.get('commission') or {}
            self._wof_save_commission(part_line, commission, sizes, is_area=is_area)
            if is_area:
                # Parts' settings are kept for both sources: with «مستقلة» they
                # weigh the parts' shares when the area splits by part.
                self._wof_save_area_parts(part_line, item.get('templates'), sizes)
                if commission.get('source') == 'from_parts':
                    areas_from_parts |= part_line
        self.film_part_line_ids.invalidate_recordset()
        for area_line in areas_from_parts:
            self._wof_sync_area_commission(area_line, sizes)
        return self.wof_matrix_load()

    # ---------------------------------------------------------------- actions
    def action_open_pricing_matrix(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'wof_pricing_matrix',
            'name': _('التسعير والعمولة · %s') % self.display_name,
            'params': {'film_id': self.id, 'wizard_id': self.env.context.get('wof_matrix_wizard_id') or False},
            'target': 'current',
        }
