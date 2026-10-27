# -*- coding: utf-8 -*-
"""The system is no longer split by branch (company).

* Settings (activities, films, sizes, components, tint shades, prices) are
  shared by every branch, and there is one setup profile for the whole system.
* Installation orders stay owned by the branch that invoices them, but every
  branch can see them.

This script prepares the data before the ORM applies the new constraints:
it keeps a single setup profile, frees the old NOT NULL company columns,
renames records that would collide once uniqueness is no longer per company,
and drops the per-company record rules.
"""

import json
import re

COMPANY_RULES = (
    'company_profile_rule', 'audit_log_company_rule',
    'setup_size_line_company_rule', 'setup_service_line_company_rule',
    'service_type_company_rule', 'film_category_company_rule',
    'film_category_line_company_rule', 'film_part_line_company_rule',
    'film_price_line_company_rule', 'film_commission_line_company_rule',
    'car_size_company_rule', 'car_part_company_rule',
    'installation_order_company_rule', 'installation_order_line_company_rule',
    'installation_material_line_company_rule',
    'installation_order_event_company_rule',
    'setup_tint_shade_line_company_rule', 'tint_degree_company_rule',
)

# Tables whose company column was required and is no longer written.
REQUIRED_COMPANY_TABLES = (
    'wof_company_profile', 'wof_car_size', 'wof_tint_degree',
    'wof_service_type', 'wof_car_parts',
)

# (table, columns that must become unique without the company).
UNIQUE_KEYS = (
    ('wof_car_size', ('name',)),
    ('wof_car_size', ('code',)),
    ('wof_tint_degree', ('value',)),
    ('wof_tint_degree', ('code',)),
    ('wof_service_type', ('name',)),
    ('wof_service_type', ('code',)),
    ('wof_car_parts', ('name',)),
    ('wof_car_parts', ('code',)),
    ('wof_film_category', ('code',)),
    ('wof_film_category', ('name', 'service_type_id')),
    ('wof_installation_order', ('name',)),
)


def _table_exists(cr, table):
    cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = %s", (table,))
    return bool(cr.fetchone())


def _column_type(cr, table, column):
    cr.execute("""
        SELECT data_type FROM information_schema.columns
         WHERE table_name = %s AND column_name = %s
    """, (table, column))
    row = cr.fetchone()
    return row and row[0]


def _keep_single_profile(cr):
    if not _table_exists(cr, 'wof_company_profile'):
        return
    cr.execute("""
        SELECT id FROM wof_company_profile
         ORDER BY (state = 'ready') DESC, id
    """)
    ids = [row[0] for row in cr.fetchall()]
    if len(ids) > 1:
        # Draft lines hang off the profile with ON DELETE CASCADE.
        cr.execute("DELETE FROM wof_company_profile WHERE id IN %s", (tuple(ids[1:]),))


def _free_company_columns(cr):
    for table in REQUIRED_COMPANY_TABLES:
        if _column_type(cr, table, 'company_id'):
            cr.execute('ALTER TABLE "%s" ALTER COLUMN company_id DROP NOT NULL' % table)


# Master lists where a branch copy is a pure duplicate: archive the copies
# so films and the pricing matrix do not show the same size or shade twice.
ARCHIVE_DUPLICATES = ('wof_car_size', 'wof_tint_degree')


def _rename_duplicates(cr, table, columns):
    """Suffix every duplicate after the first with its id so it stays unique."""
    if not _table_exists(cr, table):
        return
    if any(not _column_type(cr, table, column) for column in columns):
        return
    target = columns[0]
    keys = ', '.join('"%s"' % column for column in columns)
    cr.execute("""
        SELECT id FROM (
            SELECT id, row_number() OVER (PARTITION BY %s ORDER BY id) AS position
              FROM "%s"
             WHERE "%s" IS NOT NULL
        ) ranked
         WHERE position > 1
    """ % (keys, table, target))
    duplicate_ids = [row[0] for row in cr.fetchall()]
    if not duplicate_ids:
        return
    if _column_type(cr, table, target) == 'jsonb':
        # Translated names: suffix every language value.
        cr.execute("""
            UPDATE "%s" AS rec
               SET "%s" = (
                   SELECT jsonb_object_agg(item.key, item.value || ' (' || rec.id || ')')
                     FROM jsonb_each_text(rec."%s") AS item
               )
             WHERE rec.id IN %%s
        """ % (table, target, target), (tuple(duplicate_ids),))
    else:
        cr.execute("""
            UPDATE "%s" SET "%s" = "%s" || '-' || id WHERE id IN %%s
        """ % (table, target, target), (tuple(duplicate_ids),))
    if table in ARCHIVE_DUPLICATES and _column_type(cr, table, 'active'):
        cr.execute('UPDATE "%s" SET active = false WHERE id IN %%s' % table, (tuple(duplicate_ids),))


def _drop_company_rules(cr):
    cr.execute("""
        SELECT res_id FROM ir_model_data
         WHERE module = 'yousentech_wo_v4' AND model = 'ir.rule' AND name IN %s
    """, (COMPANY_RULES,))
    rule_ids = [row[0] for row in cr.fetchall()]
    if rule_ids:
        cr.execute("DELETE FROM ir_rule WHERE id IN %s", (tuple(rule_ids),))
    cr.execute("""
        DELETE FROM ir_model_data
         WHERE module = 'yousentech_wo_v4' AND model = 'ir.rule' AND name IN %s
    """, (COMPANY_RULES,))


def _clear_order_idempotency_duplicates(cr):
    if not _column_type(cr, 'wof_installation_order', 'idempotency_key'):
        return
    cr.execute("""
        UPDATE wof_installation_order SET idempotency_key = NULL
         WHERE id IN (
            SELECT id FROM (
                SELECT id, row_number() OVER (PARTITION BY idempotency_key ORDER BY id) AS position
                  FROM wof_installation_order
                 WHERE idempotency_key IS NOT NULL
            ) ranked WHERE position > 1
         )
    """)


def _strip_company_from_stored_views(cr):
    """Inherited views are re-validated with their stored arch before being
    reloaded from the module files, so drop company references from the stored
    copies first (the files no longer have them)."""
    cr.execute("""
        SELECT v.id, v.arch_db FROM ir_ui_view v
          JOIN ir_model_data d ON d.res_id = v.id AND d.model = 'ir.ui.view'
         WHERE d.module = 'yousentech_wo_v4' AND v.arch_db::text LIKE '%%company_id%%'
    """)
    for view_id, arch in cr.fetchall():
        if not isinstance(arch, dict):
            continue
        cleaned = {}
        for lang, value in arch.items():
            value = re.sub(r'<field name="company_id"[^>]*/>', '', value or '')
            value = value.replace("('company_id', '=', company_id), ", '')
            cleaned[lang] = value
        if cleaned != arch:
            cr.execute("UPDATE ir_ui_view SET arch_db = %s WHERE id = %s", (json.dumps(cleaned), view_id))


def migrate(cr, version):
    _strip_company_from_stored_views(cr)
    _keep_single_profile(cr)
    _free_company_columns(cr)
    for table, columns in UNIQUE_KEYS:
        _rename_duplicates(cr, table, columns)
    _clear_order_idempotency_duplicates(cr)
    _drop_company_rules(cr)
