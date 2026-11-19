# -*- coding: utf-8 -*-
"""Pending area commissions follow each part's own distribution."""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    ledger = env['wof.commission.engine']._wof_ledger()
    pending = ledger.search([('entry_type', '=', 'normal'), ('state', '=', 'pending'), ('part_line_id', '!=', False)])
    for line in pending.line_id:
        line._wof_engine_lines()._wof_commission_sync(source='تحديث توزيع الأجزاء')
