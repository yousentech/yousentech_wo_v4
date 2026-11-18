# -*- coding: utf-8 -*-
"""Create the commission ledger of the orders already past execution.

Orders sent to quality get their entries; those whose commission was approved
are frozen with today's technician weights (the old weights were not kept),
marked as carried over from the previous system.
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    source = 'مرحّلة من النظام السابق'
    orders = env['wof.installation.order'].search([('state', 'in', ('quality', 'ready', 'delivered'))])
    for order in orders:
        order.line_ids._wof_engine_lines().with_context(wof_commission_no_task_check=True)._wof_commission_sync(
            source=source)
