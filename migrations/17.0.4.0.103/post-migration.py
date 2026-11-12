# -*- coding: utf-8 -*-
"""Map the old values onto the new people fields.

* advisor / supervisor (users) -> their employee in the order's branch;
* salesperson (user) -> the salesman linked to that user;
* order technicians and service execution technician -> technicians of each service.
"""

from odoo import api, SUPERUSER_ID


def _has_column(cr, table, column):
    cr.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
        (table, column),
    )
    return bool(cr.fetchone())


def _employee(env, user, company, cache):
    key = (user.id, company.id)
    if key not in cache:
        Employee = env['hr.employee'].with_context(active_test=False)
        employee = Employee.search([('user_id', '=', user.id), ('company_id', '=', company.id)], limit=1) \
            or Employee.search([('user_id', '=', user.id)], limit=1)
        if not employee:
            employee = Employee.create({'name': user.name, 'user_id': user.id, 'company_id': company.id})
        cache[key] = employee
    return cache[key]


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {'tracking_disable': True, 'wof_skip_technician_check': True})
    Order = env['wof.installation.order'].with_context(active_test=False)
    cache = {}
    table = 'wof_installation_order'

    for legacy, field in (('wof_legacy_advisor_user_id', 'advisor_id'),
                          ('wof_legacy_supervisor_user_id', 'supervisor_id')):
        if not _has_column(cr, table, legacy):
            continue
        cr.execute(f'SELECT id, {legacy} FROM {table} WHERE {legacy} IS NOT NULL AND {field} IS NULL')
        for order_id, user_id in cr.fetchall():
            order = Order.browse(order_id).exists()
            user = env['res.users'].browse(user_id).exists()
            if order and user:
                employee = _employee(env, user, order.company_id, cache)
                cr.execute(f'UPDATE {table} SET {field} = %s WHERE id = %s', (employee.id, order_id))

    if _has_column(cr, table, 'wof_legacy_salesperson_user_id'):
        cr.execute(f'SELECT id, wof_legacy_salesperson_user_id FROM {table} '
                   f'WHERE wof_legacy_salesperson_user_id IS NOT NULL AND salesperson_id IS NULL')
        Salesman = env['salesman'].with_context(active_test=False)
        for order_id, user_id in cr.fetchall():
            order = Order.browse(order_id).exists()
            if not order:
                continue
            salesman = Salesman.search([('sale_user', '=', user_id), ('company_id', '=', order.company_id.id)], limit=1) \
                or Salesman.search([('sale_user', '=', user_id)], limit=1)
            if salesman:
                cr.execute(f'UPDATE {table} SET salesperson_id = %s WHERE id = %s', (salesman.id, order_id))

    # Technicians: per service now. Sources: assignments (17.0.4.0.102) or the
    # older user-based tables kept aside by the 17.0.4.0.102 pre-migration.
    by_order, line_tech = {}, {}
    cr.execute("SELECT to_regclass('wof_installation_order_technician')")
    if cr.fetchone()[0]:
        cr.execute('SELECT order_id, employee_id FROM wof_installation_order_technician')
        for order_id, employee_id in cr.fetchall():
            by_order.setdefault(order_id, []).append(employee_id)
        if _has_column(cr, 'wof_installation_order_line', 'execution_technician_id'):
            cr.execute("""
                SELECT l.id, t.employee_id FROM wof_installation_order_line l
                JOIN wof_installation_order_technician t ON t.id = l.execution_technician_id
            """)
            line_tech.update(dict(cr.fetchall()))
    cr.execute("SELECT to_regclass('wof_legacy_order_technician_rel')")
    if cr.fetchone()[0]:
        cr.execute('SELECT order_id, user_id FROM wof_legacy_order_technician_rel')
        for order_id, user_id in cr.fetchall():
            order = Order.browse(order_id).exists()
            user = env['res.users'].browse(user_id).exists()
            if order and user:
                employee = _employee(env, user, order.company_id, cache)
                if employee.id not in by_order.setdefault(order_id, []):
                    by_order[order_id].append(employee.id)
    if _has_column(cr, 'wof_installation_order_line', 'wof_legacy_execution_user_id'):
        cr.execute("""SELECT id, order_id, wof_legacy_execution_user_id FROM wof_installation_order_line
                      WHERE wof_legacy_execution_user_id IS NOT NULL""")
        for line_id, order_id, user_id in cr.fetchall():
            order = Order.browse(order_id).exists()
            user = env['res.users'].browse(user_id).exists()
            if order and user and line_id not in line_tech:
                line_tech[line_id] = _employee(env, user, order.company_id, cache).id
    for employee_id in {e for ids in by_order.values() for e in ids} | set(line_tech.values()):
        env['hr.employee'].browse(employee_id).exists().write({'is_wof_technician': True})
    if by_order or line_tech:
        cr.execute('SELECT id, order_id FROM wof_installation_order_line')
        pairs = []
        for line_id, order_id in cr.fetchall():
            employees = [line_tech[line_id]] if line_id in line_tech else by_order.get(order_id, [])
            pairs += [(line_id, employee_id) for employee_id in employees]
        for line_id, employee_id in pairs:
            cr.execute("""
                INSERT INTO wof_order_line_technician_rel (line_id, employee_id) VALUES (%s, %s)
                ON CONFLICT DO NOTHING
            """, (line_id, employee_id))
        lines = env['wof.installation.order.line'].browse([line_id for line_id, _e in pairs])
        if lines:
            lines.invalidate_recordset(['technician_ids'])
            env.add_to_compute(lines._fields['technician_names'], lines)
            orders = lines.order_id
            env.add_to_compute(orders._fields['technician_names'], orders)
            env.flush_all()
