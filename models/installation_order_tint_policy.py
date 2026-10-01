# -*- coding: utf-8 -*-

from odoo import api, fields, models


class InstallationOrderLineTintPolicy(models.Model):
    _inherit = 'wof.installation.order.line'

    tint_warning = fields.Char(
        string='تحذير درجة اللون',
        compute='_compute_tint_warning',
    )
    has_tint_warning = fields.Boolean(
        string='درجة لون مخالفة',
        compute='_compute_tint_warning',
    )

    @api.depends('film_category_id', 'car_part_id', 'film_category_line_id')
    def _compute_tint_warning(self):
        PartLine = self.env['wof.film.parts.lines']
        for line in self:
            line.tint_warning = False
            line.has_tint_warning = False
            if (
                not line.supports_color_grades
                or not line.film_category_id
                or not line.car_part_id
                or not line.film_category_line_id
            ):
                continue
            policy = PartLine.search([
                ('header_id', '=', line.film_category_id.id),
                ('car_part_id', '=', line.car_part_id.id),
                ('company_id', '=', line.company_id.id),
                ('part_selected', '=', True),
            ], limit=1)
            if (
                not policy
                or policy.part_type != 'car_part'
                or not policy.allowed_grade_ids
                or line.film_category_line_id in policy.allowed_grade_ids
            ):
                continue
            line.has_tint_warning = True
            line.tint_warning = (
                policy.warning_msg
                or 'درجة اللون المختارة غير مسموحة لهذا المكوّن.'
            )
