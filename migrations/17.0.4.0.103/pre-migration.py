# -*- coding: utf-8 -*-
"""Advisor and supervisor move to HR employees, the salesman to the salesmen
module: keep the old user values aside so the new columns start clean."""

LEGACY = {
    'advisor_id': 'wof_legacy_advisor_user_id',
    'supervisor_id': 'wof_legacy_supervisor_user_id',
    'salesperson_id': 'wof_legacy_salesperson_user_id',
}


def _column_exists(cr, table, column):
    cr.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
        (table, column),
    )
    return bool(cr.fetchone())


def migrate(cr, version):
    table = 'wof_installation_order'
    for column, legacy in LEGACY.items():
        if _column_exists(cr, table, column) and not _column_exists(cr, table, legacy):
            cr.execute(f'ALTER TABLE {table} RENAME COLUMN {column} TO {legacy}')
            cr.execute(f'ALTER TABLE {table} ALTER COLUMN {legacy} DROP NOT NULL')
