from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    wo_setup_completed = fields.Boolean(
        string="تمت التهيئة",
        config_parameter='yousentech_wo_v4.setup_completed'
    )



    # =========================
    # RE-SETUP
    # =========================
    def action_re_setup_wo_v4(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'yousentech_wo_v4.setup_completed',
            False
        )

        self.env['wof.setup.wizard'].reset_setup_temp_data()

        wizard = self.env['wof.setup.wizard'].create({})

        action = self.env.ref(
            'yousentech_wo_v4.action_wof_setup_wizard'
        ).read()[0]

        action['res_id'] = wizard.id
        return action