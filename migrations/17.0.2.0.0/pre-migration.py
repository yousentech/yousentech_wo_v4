# -*- coding: utf-8 -*-

import uuid


CORE_UUID_TABLES = (
    'res_company',
    'res_users',
    'res_partner',
    'product_product',
)

UUID_TABLES = (
    'wof_service_type',
    'wof_car_size',
    'wof_car_parts',
    'wof_film_category',
    'wof_film_category_lines',
    'wof_film_parts_lines',
    'wof_film_parts_price_lines',
    'wof_film_parts_commission_lines',
    'wof_car_manufactory',
    'wof_car_type',
    'wof_car_manufactory_year',
    'wof_car_agency',
    'wof_car_part_options',
    'wof_parts_transparency_level',
)

LEGACY_CODE_TABLES = (
    ('wof_service_type', 'LEGACY-SERVICE'),
    ('wof_car_size', 'LEGACY-SIZE'),
    ('wof_car_parts', 'LEGACY-PART'),
    ('wof_film_category', 'LEGACY-FILM'),
    ('wof_film_category_lines', 'LEGACY-GRADE'),
    ('wof_car_manufactory', 'LEGACY-MAKE'),
    ('wof_car_type', 'LEGACY-MODEL'),
    ('wof_car_manufactory_year', 'LEGACY-YEAR'),
    ('wof_car_agency', 'LEGACY-AGENCY'),
    ('wof_car_part_options', 'LEGACY-OPTION'),
    ('wof_parts_transparency_level', 'LEGACY-TRANSPARENCY'),
)


def _table_exists(cr, table):
    cr.execute('SELECT to_regclass(%s)', (table,))
    return bool(cr.fetchone()[0])


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


def _column_data_type(cr, table, column):
    cr.execute(
        """
        SELECT data_type
          FROM information_schema.columns
         WHERE table_schema = current_schema()
           AND table_name = %s
           AND column_name = %s
        """,
        (table, column),
    )
    row = cr.fetchone()
    return row[0] if row else None


def _backfill_public_uuids(cr, table, column='public_uuid'):
    if not _table_exists(cr, table):
        return
    if not _column_exists(cr, table, column):
        cr.execute(
            'ALTER TABLE "%s" ADD COLUMN "%s" varchar' % (table, column)
        )
    cr.execute(
        'SELECT id FROM "%s" WHERE "%s" IS NULL OR "%s" = %s'
        % (table, column, column, '%s'),
        ('',),
    )
    for (record_id,) in cr.fetchall():
        cr.execute(
            'UPDATE "%s" SET "%s" = %s WHERE id = %s'
            % (table, column, '%s', '%s'),
            (str(uuid.uuid4()), record_id),
        )


def _backfill_legacy_codes(cr, table, prefix):
    if not _table_exists(cr, table):
        return
    if not _column_exists(cr, table, 'code'):
        cr.execute('ALTER TABLE "%s" ADD COLUMN code varchar' % table)
    cr.execute(
        'UPDATE "%s" SET code = %s || %s WHERE code IS NULL OR btrim(code) = %s'
        % (table, '%s', 'id::text', '%s'),
        (prefix + '-', ''),
    )


def _backfill_source(cr, table, column):
    if not _table_exists(cr, table):
        return
    if not _column_exists(cr, table, column):
        cr.execute(
            'ALTER TABLE "%s" ADD COLUMN "%s" varchar' % (table, column)
        )
    cr.execute(
        'UPDATE "%s" SET "%s" = %s '
        'WHERE "%s" IS NULL OR "%s" = %s'
        % (table, column, '%s', column, column, '%s'),
        ('import', ''),
    )


def _backfill_orphan_car_types(cr):
    if not (
        _table_exists(cr, 'wof_car_type')
        and _table_exists(cr, 'wof_car_manufactory')
        and _column_exists(cr, 'wof_car_type', 'manufactory_id')
    ):
        return
    cr.execute(
        'SELECT 1 FROM wof_car_type WHERE manufactory_id IS NULL LIMIT 1'
    )
    if not cr.fetchone():
        return
    cr.execute(
        'SELECT id FROM wof_car_manufactory WHERE code = %s LIMIT 1',
        ('LEGACY-UNKNOWN',),
    )
    row = cr.fetchone()
    if row:
        manufactory_id = row[0]
    else:
        if _column_data_type(cr, 'wof_car_manufactory', 'name') == 'jsonb':
            cr.execute(
                """
                INSERT INTO wof_car_manufactory
                    (name, code, public_uuid, operation_source)
                VALUES (jsonb_build_object('en_US', %s), %s, %s, %s)
                RETURNING id
                """,
                (
                    'غير محدد (ترحيل)', 'LEGACY-UNKNOWN',
                    str(uuid.uuid4()), 'import',
                ),
            )
        else:
            cr.execute(
                """
                INSERT INTO wof_car_manufactory
                    (name, code, public_uuid, operation_source)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (
                    'غير محدد (ترحيل)', 'LEGACY-UNKNOWN',
                    str(uuid.uuid4()), 'import',
                ),
            )
        manufactory_id = cr.fetchone()[0]
    cr.execute(
        'UPDATE wof_car_type SET manufactory_id = %s '
        'WHERE manufactory_id IS NULL',
        (manufactory_id,),
    )


def migrate(cr, version):
    for table in CORE_UUID_TABLES:
        _backfill_public_uuids(cr, table, 'wof_public_uuid')
    _backfill_source(cr, 'product_product', 'wof_operation_source')
    for table in UUID_TABLES:
        _backfill_public_uuids(cr, table)
        _backfill_source(cr, table, 'operation_source')
    for table, prefix in LEGACY_CODE_TABLES:
        _backfill_legacy_codes(cr, table, prefix)
    _backfill_orphan_car_types(cr)
