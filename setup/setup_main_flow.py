# -*- coding: utf-8 -*-

from odoo import api, models, _


class WofMainSetupFlowMixin(models.AbstractModel):
    _name = 'wof.main.setup.flow.mixin'
    _description = 'Main Tables Setup Flow Helpers'

    @api.model
    def _parent_company(self):
        company = self.env.company
        return company.parent_id or company

    @api.model
    def _read_action(self, xmlid):
        return self.env.ref(xmlid).sudo().read()[0]


class WofSystemSettingsMainSetup(models.Model):
    _inherit = 'wof.system.settings'

    @api.model
    def action_open_main_setup_flow(self):
        self.env['wof.default.data.loader'].sudo().load_default_master_data()
        return self.env['wof.service.type'].action_open_main_setup_services()

    def action_reset_default_master_data(self):
        self.ensure_one()
        self.env['wof.default.data.loader'].sudo().reset_default_master_data(self.company_id)
        return self.env['wof.service.type'].action_open_main_setup_services()


class WofServiceTypeSetupFlow(models.Model):
    _inherit = 'wof.service.type'

    @api.model
    def action_open_main_setup_services(self):
        self.env['wof.default.data.loader'].sudo().load_default_master_data()
        company = self.env.company.parent_id or self.env.company
        action = self.env.ref('yousentech_wo_v4.action_wof_main_setup_services').sudo().read()[0]
        action['domain'] = [('company_id', '=', company.id), ('is_default_setup', '=', True)]
        action['context'] = {'create': True, 'delete': False, 'search_default_default_setup': 1, 'active_test': False}
        return action

    def action_main_setup_next_parts(self):
        return self.env['wof.car.parts'].action_open_main_setup_parts()


class WofCarPartsSetupFlow(models.Model):
    _inherit = 'wof.car.parts'

    @api.model
    def action_open_main_setup_parts(self):
        self.env['wof.default.data.loader'].sudo().load_default_master_data()
        company = self.env.company.parent_id or self.env.company
        action = self.env.ref('yousentech_wo_v4.action_wof_main_setup_parts').sudo().read()[0]
        action['domain'] = [('company_id', '=', company.id), ('is_default_setup', '=', True)]
        action['context'] = {'create': True, 'delete': False, 'search_default_default_setup': 1, 'active_test': False}
        return action

    def action_main_setup_back_services(self):
        return self.env['wof.service.type'].action_open_main_setup_services()

    def action_main_setup_next_tints(self):
        return self.env['wof.tint.degree'].action_open_main_setup_tints()


class WofTintDegreeSetupFlow(models.Model):
    _inherit = 'wof.tint.degree'

    @api.model
    def action_open_main_setup_tints(self):
        self.env['wof.default.data.loader'].sudo().load_default_master_data()
        company = self.env.company.parent_id or self.env.company
        action = self.env.ref('yousentech_wo_v4.action_wof_main_setup_tints').sudo().read()[0]
        action['domain'] = [('company_id', '=', company.id), ('is_default_setup', '=', True)]
        action['context'] = {'create': True, 'delete': False, 'search_default_default_setup': 1, 'active_test': False}
        return action

    def action_main_setup_back_parts(self):
        return self.env['wof.car.parts'].action_open_main_setup_parts()

    def action_main_setup_next_sizes(self):
        return self.env['wof.car.size'].action_open_main_setup_sizes()


class WofCarSizeSetupFlow(models.Model):
    _inherit = 'wof.car.size'

    @api.model
    def action_open_main_setup_sizes(self):
        self.env['wof.default.data.loader'].sudo().load_default_master_data()
        action = self.env.ref('yousentech_wo_v4.action_wof_main_setup_sizes').sudo().read()[0]
        action['domain'] = [('is_default_setup', '=', True)]
        action['context'] = {'create': True, 'delete': False, 'search_default_default_setup': 1, 'active_test': False}
        return action

    def action_main_setup_back_tints(self):
        return self.env['wof.tint.degree'].action_open_main_setup_tints()

    def action_main_setup_next_settings(self):
        settings = self.env['wof.system.settings'].sudo().get_company_settings()
        self.env['ir.config_parameter'].sudo().set_param('yousentech_wo_v4.setup_completed', True)
        return {
            'type': 'ir.actions.act_window',
            'name': _('الإعدادات العامة'),
            'res_model': 'wof.system.settings',
            'view_mode': 'form',
            'res_id': settings.id,
            'target': 'current',
            'context': {'create': False, 'delete': False},
            'flags': {'mode': 'edit'},
        }
