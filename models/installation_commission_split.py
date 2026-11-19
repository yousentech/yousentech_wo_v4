# -*- coding: utf-8 -*-
"""How the technician commission of a service is split (shown in the details).

The rule comes from the film component: equally, by each technician's ratio in
the installation team, or by part (service areas: each part gets its share of
the service commission in proportion to its own commission in the film, split
between that part's technicians the way the part itself is set up: equally or
by technician ratio).
"""

from odoo import api, fields, models

DISTRIBUTIONS = [
    ('equal', 'بالتساوي بين الفنيين'),
    ('by_technician_ratio', 'حسب نسبة الفني'),
    ('by_part', 'كل جزء حسب تهيئته'),
]


class WofOrderLineCommissionSplit(models.Model):
    _inherit = 'wof.installation.order.line'

    commission_distribution = fields.Selection(
        DISTRIBUTIONS, string='توزيع العمولة', compute='_compute_commission_split')
    commission_split = fields.Char(string='نصيب كل فني', compute='_compute_commission_split')

    def _wof_rule_line(self):
        return self.env['wof.film.parts.lines'].search([
            ('header_id', '=', self.film_category_id.id), ('car_part_id', '=', self.car_part_id.id),
            ('part_selected', '=', True),
        ], limit=1)

    def _wof_employee_names(self, ids):
        if not ids:
            return {}
        self.env['hr.employee'].flush_model(['name'])
        self.env.cr.execute("SELECT id, name FROM hr_employee WHERE id IN %s", (tuple(ids),))
        return dict(self.env.cr.fetchall())

    def _wof_area_setup(self):
        """(film, area line, template) of a service-area service, read with the engine rights
        (the parts' settings are commission data the counter staff may not read)."""
        self.ensure_one()
        engine = self.env['wof.commission.engine']._wof_ledger().env
        film = engine['wof.film.category'].browse(self.film_category_id.id)
        area_line = film.film_part_line_ids.filtered(
            lambda line: line.car_part_id == self.car_part_id and line.part_selected)[:1]
        template = self.service_area_template_id or self.car_part_id.default_template_id
        return film, area_line, engine['wof.service.area.template'].browse(template.id)

    def _wof_part_weights(self, parts):
        """{part line id: the part's commission inside the area for this car size}, or {} if unknown."""
        self.ensure_one()
        film, area_line, template = self._wof_area_setup()
        if not area_line:
            return {}
        weights = {}
        for part in parts:
            value = film._wof_area_part_value(area_line, template, part.part_id, self.car_size_id)
            if value is None:
                return {}
            weights[part.id] = value
        return weights if any(weights.values()) else {}

    def _wof_part_rule(self, part):
        """How a part of a service area splits its commission: its setting inside the area."""
        self.ensure_one()
        film, area_line, template = self._wof_area_setup()
        if not area_line:
            return 'equal'
        return film._wof_area_part_rule(area_line, template, part.part_id)

    def _wof_ratio_weights(self, ids):
        """{employee id: weight} from the branch team (equal when nobody has one)."""
        members = self.env['wof.team.member'].search([
            ('employee_id', 'in', ids), ('company_id', '=', self.order_id.company_id.id)])
        ratio = {m.employee_id.id: m.commission_ratio for m in members}
        if any(ratio.get(emp) for emp in ids):
            return {emp: ratio.get(emp, 0.0) for emp in ids}
        return {emp: 1.0 for emp in ids}

    def _wof_commission_shares(self, total=None, excluded=(), meta=None):
        """(rule, {(part line id or False, employee id): amount}, {key: weight}).

        ``meta`` (dict, filled when given): {key: {'part_rule', 'weight_total'}}.

        ``excluded``: {(part id or False, employee id)} of technicians who still
        have an open task (they do not share the commission when it requires
        the work to be finished).
        """
        self.ensure_one()
        total = (self.configured_commission or 0.0) if total is None else total
        rule = self._wof_rule_line().technician_commission_distribution or 'equal'
        blocked = {emp for _part, emp in excluded}
        shares, weights = {}, {}
        if self.part_line_ids and rule == 'by_part':
            self.env['wof.installation.order.line.part'].flush_model(['technician_ids'])
            working = {}
            for part in self.part_line_ids:
                self.env.cr.execute(
                    "SELECT employee_id FROM wof_order_line_part_technician_rel WHERE part_line_id = %s ORDER BY employee_id",
                    (part.id,))
                ids = [row[0] for row in self.env.cr.fetchall() if (part.id, row[0]) not in excluded
                       and (False, row[0]) not in excluded]
                if ids:
                    working[part] = ids
            if not working:
                return rule, shares, weights
            # Each part weighs its own commission in the film (front 10, rear 20);
            # equal parts when the film gives no per-part commission.
            part_weights = self._wof_part_weights(list(working)) or {part.id: 1.0 for part in working}
            total_weight = sum(part_weights[part.id] for part in working) or 1.0
            for part, ids in working.items():
                part_amount = total * part_weights[part.id] / total_weight
                part_rule = self._wof_part_rule(part)
                emp_weights = self._wof_ratio_weights(ids) if part_rule == 'by_technician_ratio' \
                    else {emp: 1.0 for emp in ids}
                emp_total = sum(emp_weights.values()) or 1.0
                for emp in ids:
                    shares[(part.id, emp)] = part_amount * emp_weights[emp] / emp_total
                    weights[(part.id, emp)] = emp_weights[emp] if part_rule == 'by_technician_ratio' else 0.0
                    if meta is not None:
                        meta[(part.id, emp)] = {'part_rule': part_rule, 'weight_total': emp_total
                                                if part_rule == 'by_technician_ratio' else 0.0}
            return rule, shares, weights
        self.flush_model(['technician_ids'])
        self.env.cr.execute(
            "SELECT employee_id FROM wof_order_line_technician_rel WHERE line_id = %s ORDER BY employee_id", (self.id,))
        ids = [row[0] for row in self.env.cr.fetchall() if row[0] not in blocked]
        if not ids:
            return rule, shares, weights
        if rule == 'by_part' and not self.part_line_ids:
            rule = 'equal'
        emp_weights = self._wof_ratio_weights(ids) if rule == 'by_technician_ratio' else {emp: 1.0 for emp in ids}
        total_weight = sum(emp_weights.values()) or 1.0
        shares = {(False, emp): total * weight / total_weight for emp, weight in emp_weights.items()}
        if rule == 'by_technician_ratio':
            weights = {(False, emp): weight for emp, weight in emp_weights.items()}
            if meta is not None:
                meta.update({(False, emp): {'part_rule': False, 'weight_total': total_weight} for emp in ids})
        return rule, shares, weights

    @api.depends('configured_commission', 'technician_ids', 'part_line_ids.technician_ids',
                 'film_category_id', 'car_part_id')
    def _compute_commission_split(self):
        for line in self:
            line.commission_distribution = False
            line.commission_split = False
            if not line.id or not line.film_category_id:
                continue
            frozen = line._wof_entries(types=('normal', 'reversal', 'adjustment')) \
                if 'commission_entry_ids' in line._fields else []
            if frozen:
                rule = frozen.filtered(lambda entry: entry.entry_type == 'normal')[:1].distribution \
                    or line._wof_rule_line().technician_commission_distribution or 'equal'
                shares = {}
                for entry in frozen:
                    shares[entry.employee_id.id] = shares.get(entry.employee_id.id, 0.0) + entry.amount
            else:
                rule, plan = line._wof_commission_plan()
                shares = {}
                for (_part, emp), (amount, *_rest) in plan.items():
                    shares[emp] = shares.get(emp, 0.0) + amount
            line.commission_distribution = rule if rule in dict(DISTRIBUTIONS) else False
            names = line._wof_employee_names(list(shares))
            symbol = line.currency_id.symbol or ''
            line.commission_split = ' · '.join(
                '%s %.2f %s' % (names.get(emp, ''), amount, symbol) for emp, amount in shares.items()) or False
