# -*- coding: utf-8 -*-
from odoo import models, fields, api

class WofSetupWizard(models.TransientModel):
    _name = 'wof.setup.wizard'
    _description = 'WOF Setup Wizard'


   
    # =========================
    # FINISH SETUP
    # =========================
    def action_finish_setup(self):

        self.env['ir.config_parameter'].sudo().set_param(
            'yousentech_wo_v4.setup_completed',
            True
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }