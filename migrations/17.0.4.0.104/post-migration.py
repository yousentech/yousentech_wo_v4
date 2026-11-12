# -*- coding: utf-8 -*-
"""Employees already used as operations supervisors get the «مشرف تشغيل» flag,
and existing orders are linked to customer vehicle records."""

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {'tracking_disable': True})
    orders = env['wof.installation.order'].with_context(active_test=False).search([])
    orders.supervisor_id.write({'is_wof_supervisor': True})
    for order in orders.filtered(lambda rec: rec.vehicle_plate and not rec.vehicle_id).sorted('id'):
        order._wof_sync_vehicle()
