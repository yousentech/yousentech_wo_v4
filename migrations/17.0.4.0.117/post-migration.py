# -*- coding: utf-8 -*-
"""Technician tasks for the services of open orders; vehicle condition defaults to good."""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    lines = env['wof.installation.order.line'].search([('order_id.state', 'not in', ('delivered', 'cancelled'))])
    lines._wof_sync_tasks()
    # Finished work keeps its progress: mark tasks of services already at 100% as done.
    for line in lines.filtered(lambda rec: rec.execution_progress == 100):
        line.task_ids.with_context(wof_task_internal=True).write({'done': True})
    cr.execute("UPDATE wof_installation_order SET intake_condition = 'good' "
               "WHERE intake_condition IS NULL AND state IN ('draft', 'scheduled')")
