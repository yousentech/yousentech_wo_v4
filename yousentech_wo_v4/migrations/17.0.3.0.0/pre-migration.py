# -*- coding: utf-8 -*-

import uuid


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


def migrate(cr, version):
    """Backfill the public customer identity before the required ORM field."""
    if not _column_exists(cr, 'res_partner', 'wof_public_uuid'):
        cr.execute(
            'ALTER TABLE res_partner ADD COLUMN wof_public_uuid varchar'
        )
    cr.execute(
        'SELECT id FROM res_partner '
        'WHERE wof_public_uuid IS NULL OR wof_public_uuid = %s',
        ('',),
    )
    for (record_id,) in cr.fetchall():
        cr.execute(
            'UPDATE res_partner SET wof_public_uuid = %s WHERE id = %s',
            (str(uuid.uuid4()), record_id),
        )
