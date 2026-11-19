# -*- coding: utf-8 -*-
"""Parts inside service areas get their own commission setting.

Before, a part inside an area shared its film line with the part sold alone.
Now every part of every template of the area has its own setting:
* sold alone in the film: «حسب تهيئة الجزء» (same values as before);
* only inside the area: its former values become the area's own values
  (amounts; a former percentage had no price to apply to and is left empty).
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Config = env['wof.film.area.part.commission']
    area_lines = env['wof.film.parts.lines'].search([('car_part_id.part_type', '=', 'service_area')])
    for area_line in area_lines:
        film = area_line.header_id
        for template in film._wof_area_templates(area_line.car_part_id):
            for index, part in enumerate(template.component_ids, start=1):
                if film._wof_area_config(area_line, template, part):
                    continue
                standalone = film._wof_standalone_line(part)
                basis = film.film_part_line_ids.filtered(lambda line: line.car_part_id == part)[:1]
                vals = {'area_line_id': area_line.id, 'template_id': template.id, 'part_id': part.id,
                        'sequence': index}
                if standalone:
                    vals.update(method='part', distribution='part')
                elif basis:
                    by_size = basis.commission_calculation_policy == 'by_size'
                    rule = basis.technician_commission_distribution
                    vals.update(method='by_size' if by_size else 'fixed',
                                distribution=rule if rule in ('equal', 'by_technician_ratio') else 'equal')
                    if basis.commission_value_type != 'percent':
                        vals['value_ids'] = [(0, 0, {'car_size_id': line.car_size_id.id or False,
                                                     'amount': line.commission})
                                             for line in basis.commission_line_ids
                                             if bool(line.car_size_id) == by_size]
                else:
                    vals.update(method='fixed', distribution='equal')
                Config.create(vals)
        if area_line.service_commission_source == 'from_parts':
            film._wof_sync_area_commission(area_line, film._wof_matrix_sizes())
