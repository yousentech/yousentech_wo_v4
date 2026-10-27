# -*- coding: utf-8 -*-
"""Warranty becomes period + unit (day/month/year).

Create the new columns before the ORM does, so existing films keep their
warranty in years instead of receiving the field default.
"""


def migrate(cr, version):
    cr.execute("""
        ALTER TABLE wof_film_category
            ADD COLUMN IF NOT EXISTS warranty_period integer,
            ADD COLUMN IF NOT EXISTS warranty_unit varchar
    """)
    cr.execute("""
        UPDATE wof_film_category
           SET warranty_period = COALESCE(warranty_years, 0),
               warranty_unit = 'year'
         WHERE warranty_period IS NULL OR warranty_unit IS NULL
    """)
