# -*- coding: utf-8 -*-
"""Existing service-area services get their template parts, carrying the
service's grade, stock product and technicians (progress copied as is)."""

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {'wof_skip_technician_check': True, 'tracking_disable': True})
    lines = env['wof.installation.order.line'].search([('car_part_id.part_type', '=', 'service_area')])
    for line in lines.filtered(lambda rec: not rec.part_line_ids):
        cr.execute('SELECT employee_id FROM wof_order_line_technician_rel WHERE line_id = %s', (line.id,))
        technicians = [row[0] for row in cr.fetchall()]
        progress = line.execution_progress
        line._wof_build_parts()
        parts = line.part_line_ids.with_context(wof_part_internal=True)
        if parts:
            parts.write({'progress': progress, 'technician_ids': [(6, 0, technicians)]})
            line._wof_sync_from_parts()
