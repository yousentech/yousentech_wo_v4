# -*- coding: utf-8 -*-
"""The order date becomes a date (no time): convert in the main user's time zone."""


def migrate(cr, version):
    cr.execute("""
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'wof_installation_order' AND column_name = 'appointment_at'
    """)
    row = cr.fetchone()
    if not row or row[0] == 'date':
        return
    cr.execute("""
        SELECT p.tz FROM res_users u JOIN res_partner p ON p.id = u.partner_id
        WHERE u.id = 2 AND p.tz IS NOT NULL
    """)
    tz = (cr.fetchone() or ['UTC'])[0]
    cr.execute(
        "ALTER TABLE wof_installation_order ALTER COLUMN appointment_at TYPE date "
        "USING ((appointment_at AT TIME ZONE 'UTC') AT TIME ZONE %s)::date",
        (tz,),
    )
