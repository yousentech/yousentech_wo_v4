# -*- coding: utf-8 -*-
"""Pending commissions are rebuilt per part (service areas split by each part's commission).

Approved ones stay frozen; the manager may recalculate them from the order.
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    ledger = env['wof.commission.engine']._wof_ledger()
    entries = ledger.search([('entry_type', '=', 'normal'), ('state', '=', 'pending')])
    lines = entries.line_id
    for line in lines:
        mine = entries.filtered(lambda entry: entry.line_id == line)
        if ledger.search_count([('line_id', '=', line.id), ('state', 'in', ('approved', 'paid'))]):
            continue
        mine.write({'state': 'replaced', 'source': 'تحديث طريقة الحساب (لكل جزء)'})
        line._wof_engine_lines()._wof_commission_sync(source='تحديث طريقة الحساب (لكل جزء)')
    for entry in ledger.search([('car_part_id', '=', False), ('line_id', '!=', False)]):
        entry.write({'car_part_id': entry.part_line_id.part_id.id or entry.line_id.car_part_id.id})
