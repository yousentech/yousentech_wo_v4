# -*- coding: utf-8 -*-

from odoo import api, fields, models


class WofFilmSetupComponentLineTemplateCount(models.TransientModel):
    _inherit = 'wof.film.setup.component.line'

    template_component_count = fields.Integer(compute='_compute_template_component_count')

    @api.depends('template_id.component_ids')
    def _compute_template_component_count(self):
        for line in self:
            line.template_component_count = len(line.template_id.component_ids) if line.template_id else 0
