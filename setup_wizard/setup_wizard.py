# -*- coding: utf-8 -*-
from odoo import models

class WofSetupWizard(models.TransientModel):
    _name = 'wof.setup.wizard'
    _description = 'WOF Setup Wizard'


    @api.model
    def action_open_setup_wizard(self):

        setup_done = self.env['ir.config_parameter'].sudo().get_param(
            'yousentech_wo_v4.setup_completed'
        )

        if not setup_done:

            return {
                'type': 'ir.actions.act_window',
                'name': 'تهيئة النظام',
                'res_model': 'wof.setup.wizard',
                'view_mode': 'form',
                'target': 'current',
            }

        return 