# -*- coding: utf-8 -*-

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    areas = env['wof.car.parts'].with_context(active_test=False).search([
        ('part_type', '=', 'service_area'),
    ])
    areas.ensure_service_area_templates()

    # Deterministically repair legacy/default state without touching commercial data.
    for area in areas:
        templates = area.template_ids.filtered('active').sorted(lambda rec: (rec.sequence, rec.id))
        if not templates:
            continue
        defaults = templates.filtered('is_default')
        chosen = defaults[:1] or templates[:1]
        (templates - chosen).with_context(skip_default_sync=True).write({'is_default': False})
        if not chosen.is_default:
            chosen.with_context(skip_default_sync=True).write({'is_default': True})
        # Existing runtime code reads the legacy direct relation. Keep it aligned
        # with the default template until installation-order template selection ships.
        area.service_area_part_ids = [(6, 0, chosen.component_ids.ids)]
