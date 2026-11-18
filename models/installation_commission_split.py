# -*- coding: utf-8 -*-
"""How the technician commission of a service is split (shown in the details).

The rule comes from the film component: equally, by each technician's ratio in
the installation team, or by part (service areas: each part gets an equal share
of the service commission, split equally between that part's technicians).
"""

from odoo import api, fields, models

DISTRIBUTIONS = [
    ('equal', 'بالتساوي بين الفنيين'),
    ('by_technician_ratio', 'حسب نسبة الفني'),
    ('by_part', 'حسب الجزء المنفذ'),
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

    def _wof_commission_shares(self, total=None, excluded=()):
        """(rule, {employee_id: amount}, {employee_id: weight}) following the component's rule.

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
            parts = []
            for part in self.part_line_ids:
                self.env.cr.execute(
                    "SELECT employee_id FROM wof_order_line_part_technician_rel WHERE part_line_id = %s ORDER BY employee_id",
                    (part.id,))
                ids = [row[0] for row in self.env.cr.fetchall() if (part.id, row[0]) not in excluded]
                if ids:
                    parts.append(ids)
            for ids in parts:
                per_part = total / len(parts)
                for emp in ids:
                    shares[emp] = shares.get(emp, 0.0) + per_part / len(ids)
            return rule, shares, weights
        self.flush_model(['technician_ids'])
        self.env.cr.execute(
            "SELECT employee_id FROM wof_order_line_technician_rel WHERE line_id = %s ORDER BY employee_id", (self.id,))
        ids = [row[0] for row in self.env.cr.fetchall() if row[0] not in blocked]
        if not ids:
            return rule, shares, weights
        if rule == 'by_part' and not self.part_line_ids:
            rule = 'equal'
        weights = {emp: 1.0 for emp in ids}
        if rule == 'by_technician_ratio':
            members = self.env['wof.team.member'].search([
                ('employee_id', 'in', ids), ('company_id', '=', self.order_id.company_id.id)])
            ratio = {m.employee_id.id: m.commission_ratio for m in members}
            if any(ratio.get(emp) for emp in ids):
                weights = {emp: ratio.get(emp, 0.0) for emp in ids}
        total_weight = sum(weights.values()) or 1.0
        shares = {emp: total * weight / total_weight for emp, weight in weights.items()}
        if rule != 'by_technician_ratio':
            weights = {}
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
                shares = {emp: amount for emp, (amount, _weight) in plan.items()}
            line.commission_distribution = rule if rule in dict(DISTRIBUTIONS) else False
            names = line._wof_employee_names(list(shares))
            symbol = line.currency_id.symbol or ''
            line.commission_split = ' · '.join(
                '%s %.2f %s' % (names.get(emp, ''), amount, symbol) for emp, amount in shares.items()) or False
