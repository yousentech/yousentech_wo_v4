# -*- coding: utf-8 -*-
"""Map the old free-text colours onto the colours table (adding unknown ones)."""

from odoo import api, SUPERUSER_ID


def _has_column(cr, table, column):
    cr.execute("SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s", (table, column))
    return bool(cr.fetchone())


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {'active_test': False})
    Color = env['wof.car.color']
    Make = env['wof.car.manufactory']
    cache = {}

    def color_for(text):
        key = text.strip().lower()
        if key not in cache:
            from odoo.addons.yousentech_wo_v4.setup.car_catalog import CAR_COLORS
            code = next((c for c, ar, en, _h in CAR_COLORS if key in (ar.lower(), en.lower())), False)
            color = Color.search([('code', '=', code)], limit=1) if code else Color
            color = color or Make._wof_find(Color, False, [text.strip()])
            cache[key] = color or Color.create({'name': text.strip()})
        return cache[key]

    for table, old, new in (('wof_installation_order', 'vehicle_color', 'vehicle_color_id'),
                            ('wof_vehicle', 'color', 'color_id')):
        if not _has_column(cr, table, old):
            continue
        cr.execute(f"SELECT id, {old} FROM {table} WHERE {old} IS NOT NULL AND trim({old}) <> '' AND {new} IS NULL")
        for rec_id, text in cr.fetchall():
            cr.execute(f"UPDATE {table} SET {new} = %s WHERE id = %s", (color_for(text).id, rec_id))
