# -*- coding: utf-8 -*-
"""Technicians move from users to HR employees: keep the old assignments aside."""


def _table_exists(cr, table):
    cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = %s", (table,))
    return bool(cr.fetchone())


def _column_exists(cr, table, column):
    cr.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
        (table, column),
    )
    return bool(cr.fetchone())


def migrate(cr, version):
    if _table_exists(cr, 'wof_installation_order_technician_rel') \
            and not _table_exists(cr, 'wof_legacy_order_technician_rel'):
        cr.execute("ALTER TABLE wof_installation_order_technician_rel RENAME TO wof_legacy_order_technician_rel")
    if _column_exists(cr, 'wof_installation_order_line', 'execution_technician_id') \
            and not _column_exists(cr, 'wof_installation_order_line', 'wof_legacy_execution_user_id'):
        cr.execute("""
            ALTER TABLE wof_installation_order_line
            RENAME COLUMN execution_technician_id TO wof_legacy_execution_user_id
        """)
