# -*- coding: utf-8 -*-
"""Map the old user-based technicians to HR employees flagged «فني تركيب»."""

from odoo import api, SUPERUSER_ID


def _employee_for(env, user, company, cache):
    key = (user.id, company.id)
    if key in cache:
        return cache[key]
    Employee = env['hr.employee'].with_context(active_test=False)
    employee = Employee.search([('user_id', '=', user.id), ('company_id', '=', company.id)], limit=1) \
        or Employee.search([('user_id', '=', user.id)], limit=1)
    if not employee:
        employee = Employee.create({'name': user.name, 'user_id': user.id, 'company_id': company.id})
    if not employee.is_wof_technician:
        employee.is_wof_technician = True
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
