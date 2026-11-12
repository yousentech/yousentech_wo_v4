# -*- coding: utf-8 -*-
"""Map the old user-based technicians to HR employees flagged «فني تركيب»."""

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


def _employee_for(env, user, company, cache):
    key = (user.id, company.id)
    if key in cache:
        return cache[key]
    Employee = env['hr.employee'].with_context(active_test=False)
    employee = Employee.search([('user_id', '=', user.id), ('company_id', '=', company.id)], limit=1) \
        or Employee.search([('user_id', '=', user.id)], limit=1)
    if not employee:
        employee = Employee.create({'name': user.name, 'user_id': user.id, 'company_id': company.id})
    _mark_team(env, employee, company)
    cache[key] = employee
    return employee


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {'wof_skip_technician_check': True, 'tracking_disable': True})
    cache = {}

    # Users holding the technician role become technician employees, so the list is not empty.
    group = env.ref('yousentech_wo_v4.group_wo_technician', raise_if_not_found=False)
    if group:
        for user in group.users.filtered(lambda rec: rec.active and not rec.share):
            _employee_for(env, user, user.company_id, cache)
    # The old assignments are moved onto each service by the 17.0.4.0.103 migration.
