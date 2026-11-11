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
    Assignment = env['wof.installation.order.technician'].with_context(wof_skip_technician_check=True)

    # Users holding the technician role become technician employees, so the list is not empty.
    group = env.ref('yousentech_wo_v4.group_wo_technician', raise_if_not_found=False)
    if group:
        for user in group.users.filtered(lambda rec: rec.active and not rec.share):
            _employee_for(env, user, user.company_id, cache)

    cr.execute("SELECT to_regclass('wof_legacy_order_technician_rel')")
    if cr.fetchone()[0]:
        cr.execute("SELECT order_id, user_id FROM wof_legacy_order_technician_rel")
        for order_id, user_id in cr.fetchall():
            order = env['wof.installation.order'].browse(order_id).exists()
            user = env['res.users'].browse(user_id).exists()
            if not order or not user:
                continue
            employee = _employee_for(env, user, order.company_id, cache)
            if not Assignment.search_count([('order_id', '=', order.id), ('employee_id', '=', employee.id)]):
                Assignment.create({'order_id': order.id, 'employee_id': employee.id})

    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'wof_installation_order_line' AND column_name = 'wof_legacy_execution_user_id'
    """)
    if cr.fetchone():
        cr.execute("""
            SELECT id, order_id, wof_legacy_execution_user_id FROM wof_installation_order_line
            WHERE wof_legacy_execution_user_id IS NOT NULL
        """)
        for line_id, order_id, user_id in cr.fetchall():
            order = env['wof.installation.order'].browse(order_id).exists()
            user = env['res.users'].browse(user_id).exists()
            if not order or not user:
                continue
            employee = _employee_for(env, user, order.company_id, cache)
            assignment = Assignment.search([('order_id', '=', order.id), ('employee_id', '=', employee.id)], limit=1) \
                or Assignment.create({'order_id': order.id, 'employee_id': employee.id})
            cr.execute(
                "UPDATE wof_installation_order_line SET execution_technician_id = %s WHERE id = %s",
                (assignment.id, line_id),
            )
