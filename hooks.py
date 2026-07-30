# -*- coding: utf-8 -*-

import uuid


CORE_UUID_TABLES = (
    'res_company',
    'res_users',
    'res_partner',
    'product_product',
)


def _column_exists(cr, table, column):
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = current_schema()
           AND table_name = %s
           AND column_name = %s
        """,
        (table, column),
    )
    return bool(cr.fetchone())


def pre_init_hook(env_or_cr):
    """Give existing core rows distinct UUIDs before unique fields are installed."""
    cr = getattr(env_or_cr, 'cr', env_or_cr)
    for table in CORE_UUID_TABLES:
        if not _column_exists(cr, table, 'wof_public_uuid'):
            cr.execute(
                'ALTER TABLE "%s" ADD COLUMN wof_public_uuid varchar' % table
            )
        cr.execute(
            'SELECT id FROM "%s" '
            'WHERE wof_public_uuid IS NULL OR wof_public_uuid = %s'
            % (table, '%s'),
            ('',),
        )
        for (record_id,) in cr.fetchall():
            cr.execute(
                'UPDATE "%s" SET wof_public_uuid = %s WHERE id = %s'
                % (table, '%s', '%s'),
                (str(uuid.uuid4()), record_id),
            )
    if not _column_exists(cr, 'product_product', 'wof_operation_source'):
        cr.execute(
            'ALTER TABLE product_product '
            'ADD COLUMN wof_operation_source varchar'
        )
    cr.execute(
        'UPDATE product_product SET wof_operation_source = %s '
        'WHERE wof_operation_source IS NULL OR wof_operation_source = %s',
        ('import', ''),
    )
