# -*- coding: utf-8 -*-
"""Employees already used as operations supervisors get the «مشرف تشغيل» flag,
and existing orders are linked to customer vehicle records."""

from odoo import api, SUPERUSER_ID


def _mark_team(env, employee, company, role='technician'):
    """Record the employee as technician/supervisor with whatever this version has."""
    if not employee:
        return
    if 'wof.team.member' in env:
        Team = env['wof.team.member'].with_context(active_test=False)
        field = 'is_technician' if role == 'technician' else 'is_supervisor'
        member = Team.search([('employee_id', '=', employee.id), ('company_id', '=', company.id)], limit=1)
        if member:
            member.write({field: True, 'active': True})
        else:
            Team.create({'employee_id': employee.id, 'company_id': company.id,
                         'is_technician': role == 'technician', 'is_supervisor': role != 'technician'})
        return
    flag = 'is_wof_technician' if role == 'technician' else 'is_wof_supervisor'
    if flag in employee._fields:
        employee.write({flag: True})


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {'tracking_disable': True})
    orders = env['wof.installation.order'].with_context(active_test=False).search([])
    for order in orders.filtered('supervisor_id'):
        _mark_team(env, order.supervisor_id, order.company_id, 'supervisor')
    for order in orders.filtered(lambda rec: rec.vehicle_plate and not rec.vehicle_id).sorted('id'):
        order._wof_sync_vehicle()
