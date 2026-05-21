# -*- coding: utf-8 -*-
import ast
import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class SoftRestrictConfig(models.Model):
    _name = 'soft.restrict.config'
    _description = 'Soft Restrict Access Configuration'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    model_id = fields.Many2one(
        'ir.model',
        string='Target Model',
        required=True,
        ondelete='cascade',
        domain=[('transient', '=', False)],
    )
    model_name = fields.Char(related='model_id.model', store=True, readonly=True)

    group_id = fields.Many2one(
        'res.groups',
        string='Applied Group',
        required=True,
        default=lambda self: self.env.ref(
            'yousentech_soft_restrict.group_soft_restrict_own_records',
            raise_if_not_found=False,
        ),
        help='Users in this group will be restricted by the generated own-record rule and can use soft related access.',
    )

    owner_field_names = fields.Char(
        string='Owner User Fields',
        default='create_uid,user_id,invoice_user_id,salesman_id',
        help='Comma separated Many2one(res.users) fields. Existing fields only will be used.',
    )
    link_field_names = fields.Char(
        string='Related Document Fields',
        required=True,
        help='Comma separated relational fields. If the user can read one related record, opening this denied record is allowed.',
    )

    create_own_rule = fields.Boolean(
        string='Create Own-Records Rule',
        default=True,
        help='Create/maintain a record rule that lets the group see only records owned by the configured owner fields.',
    )
    rule_id = fields.Many2one('ir.rule', string='Generated Rule', readonly=True, copy=False)
    rule_domain = fields.Text(string='Generated Rule Domain', compute='_compute_rule_domain')

    @api.depends('owner_field_names', 'model_name')
    def _compute_rule_domain(self):
        for rec in self:
            rec.rule_domain = rec._build_own_domain_string() if rec.model_name else '[]'

    def _split_names(self, value):
        return [x.strip() for x in (value or '').split(',') if x.strip()]

    def _valid_owner_fields(self):
        self.ensure_one()
        model = self.env[self.model_name]
        valid = []
        for fname in self._split_names(self.owner_field_names):
            field = model._fields.get(fname)
            if field and field.type == 'many2one' and field.comodel_name == 'res.users':
                valid.append(fname)
        return valid

    def _valid_link_fields(self):
        self.ensure_one()
        model = self.env[self.model_name]
        valid = []
        for fname in self._split_names(self.link_field_names):
            field = model._fields.get(fname)
            if field and field.type in ('many2one', 'one2many', 'many2many'):
                valid.append(fname)
        return valid

    def _build_own_domain(self):
        self.ensure_one()
        fields_list = self._valid_owner_fields()
        if not fields_list:
            # Safe domain: no accidental broad access.
            return [('id', '=', 0)]
        domains = [(fname, '=', self.env.user.id) for fname in fields_list]
        if len(domains) == 1:
            return domains
        return ['|'] * (len(domains) - 1) + domains

    def _build_own_domain_string(self):
        domain = self._build_own_domain()
        # Replace current user id with runtime user.id for ir.rule.
        domain_str = repr(domain)
        current_uid = repr(self.env.user.id)
        return domain_str.replace(current_uid, 'user.id')

    @api.constrains('model_id', 'owner_field_names', 'link_field_names')
    def _check_config_fields(self):
        protected_models = {
            'base', 'res.users', 'res.groups', 'ir.rule', 'ir.model',
            'ir.model.access', 'ir.config_parameter', 'ir.module.module',
        }
        for rec in self:
            if rec.model_name in protected_models:
                raise ValidationError(_('This model is protected and cannot be used with Soft Restrict: %s') % rec.model_name)

            model = self.env[rec.model_name]
            all_names = rec._split_names(rec.owner_field_names) + rec._split_names(rec.link_field_names)
            for fname in all_names:
                if fname not in model._fields:
                    raise ValidationError(_("Field '%s' does not exist on model '%s'.") % (fname, rec.model_name))

            if rec.owner_field_names and not rec._valid_owner_fields():
                raise ValidationError(_('Owner fields must contain at least one Many2one field to res.users.'))

            if not rec._valid_link_fields():
                raise ValidationError(_('Related Document Fields must contain at least one relational field.'))

    def action_sync_rule(self):
        for rec in self.sudo():
            if not rec.create_own_rule:
                if rec.rule_id:
                    rec.rule_id.active = False
                continue

            domain = rec._build_own_domain_string()
            vals = {
                'name': 'Soft Restrict Own Records - %s' % rec.model_name,
                'model_id': rec.model_id.id,
                'domain_force': domain,
                'perm_read': True,
                'perm_write': True,
                'perm_create': True,
                'perm_unlink': True,
                'active': rec.active,
                'groups': [(6, 0, rec.group_id.ids)],
            }
            if rec.rule_id:
                rec.rule_id.write(vals)
            else:
                rec.rule_id = self.env['ir.rule'].create(vals).id
        self.clear_caches()
        return True

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.filtered('create_own_rule').action_sync_rule()
        return records

    def write(self, vals):
        res = super().write(vals)
        trigger = {'active', 'model_id', 'group_id', 'owner_field_names', 'create_own_rule'}
        if trigger.intersection(vals):
            self.action_sync_rule()
        self.clear_caches()
        return res

    def unlink(self):
        rules = self.sudo().mapped('rule_id')
        res = super().unlink()
        if rules:
            rules.unlink()
        self.clear_caches()
        return res

    @api.model
    def _get_active_configs_for_model(self, model_name):
        if not self.env['ir.config_parameter'].sudo().get_param('yousentech_wo_v4.enabled'):
            return self.browse()
        return self.sudo().search([('active', '=', True), ('model_name', '=', model_name)])
