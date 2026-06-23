# -*- coding: utf-8 -*-

from odoo import api, models, _


class WofMainSetupFlowMixin(models.AbstractModel):
    _name = 'wof.main.setup.flow.mixin'
    _description = 'Main Tables Setup Flow Helpers'

    @api.model
    def _parent_company(self):
        company = self.env.company
        return company.parent_id or company


class WofSystemSettingsMainSetup(models.Model):
    _inherit = 'wof.system.settings'

    @api.model
    def action_open_main_setup_flow(self):
        """Open the permanent setup dashboard.

        The setup flow no longer uses temporary wizard tables. It uses the real
        master tables directly, while keeping the same step-by-step UX through
        dashboard buttons and setup list views.
        """
        self.env['wof.default.data.loader'].sudo().load_default_master_data()
        return self.action_open_current_company_settings()

    def action_reset_default_master_data(self):
        self.ensure_one()
        self.env['wof.default.data.loader'].sudo().reset_default_master_data(self.company_id)
        return self.action_open_main_setup_flow()

    def action_setup_services(self):
        return self.env['wof.service.type'].action_open_main_setup_services()

    def action_setup_parts(self):
        return self.env['wof.car.parts'].action_open_main_setup_parts()

    def action_setup_tints(self):
        return self.env['wof.tint.degree'].action_open_main_setup_tints()

    def action_setup_sizes(self):
        return self.env['wof.car.size'].action_open_main_setup_sizes()

    def action_finish_main_setup(self):
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param('yousentech_wo_v4.setup_completed', True)
        return self.action_open_current_company_settings()


class WofServiceTypeSetupFlow(models.Model):
    _inherit = 'wof.service.type'

    @api.model
    def action_open_main_setup_services(self):
        self.env['wof.default.data.loader'].sudo().load_default_master_data()
        company = self.env.company.parent_id or self.env.company
        action = self.env.ref('yousentech_wo_v4.action_wof_main_setup_services').sudo().read()[0]
        action['domain'] = [('company_id', '=', company.id), ('is_default_setup', '=', True)]
        action['context'] = {
            'create': True,
            'delete': False,
            'active_test': False,
            'search_default_default_setup': 1,
            'default_company_id': company.id,
            'default_is_default_setup': True,
        }
        return action


class WofCarPartsSetupFlow(models.Model):
    _inherit = 'wof.car.parts'

    @api.model
    def action_open_main_setup_parts(self):
        self.env['wof.default.data.loader'].sudo().load_default_master_data()
        company = self.env.company.parent_id or self.env.company
        action = self.env.ref('yousentech_wo_v4.action_wof_main_setup_parts').sudo().read()[0]
        action['domain'] = [('company_id', '=', company.id), ('is_default_setup', '=', True)]
        action['context'] = {
            'create': True,
            'delete': False,
            'active_test': False,
            'search_default_default_setup': 1,
            'default_company_id': company.id,
            'default_is_default_setup': True,
        }
        return action


class WofTintDegreeSetupFlow(models.Model):
    _inherit = 'wof.tint.degree'

    @api.model
    def action_open_main_setup_tints(self):
        self.env['wof.default.data.loader'].sudo().load_default_master_data()
        company = self.env.company.parent_id or self.env.company
        action = self.env.ref('yousentech_wo_v4.action_wof_main_setup_tints').sudo().read()[0]
        action['domain'] = [('company_id', '=', company.id), ('is_default_setup', '=', True)]
        action['context'] = {
            'create': True,
            'delete': False,
            'active_test': False,
            'search_default_default_setup': 1,
            'default_company_id': company.id,
            'default_is_default_setup': True,
        }
        return action


class WofCarSizeSetupFlow(models.Model):
    _inherit = 'wof.car.size'

    @api.model
    def action_open_main_setup_sizes(self):
        self.env['wof.default.data.loader'].sudo().load_default_master_data()
        action = self.env.ref('yousentech_wo_v4.action_wof_main_setup_sizes').sudo().read()[0]
        action['domain'] = [('is_default_setup', '=', True)]
        action['context'] = {
            'create': True,
            'delete': False,
            'active_test': False,
            'search_default_default_setup': 1,
            'default_is_default_setup': True,
        }
        return action
