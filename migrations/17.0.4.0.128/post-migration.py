# -*- coding: utf-8 -*-
"""Apply the credit notes posted before the commission reversal could match them."""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    refunds = env['account.move'].search([('move_type', '=', 'out_refund'), ('state', '=', 'posted')])
    refunds._wof_commission_apply_refund()
