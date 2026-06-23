from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    wo_setup_completed = fields.Boolean(
        string="تمت التهيئة",
        config_parameter='yousentech_wo_v4.setup_completed'
    )
