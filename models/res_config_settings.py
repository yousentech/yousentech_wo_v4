# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    soft_restrict_enabled = fields.Boolean(
        string='Enable Soft Restrict Access',
        config_parameter='yousentech_soft_restrict.enabled',
        default=False,
    )
