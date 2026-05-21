# -*- coding: utf-8 -*-
import logging

from odoo import models
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)


class BaseSoftRestrict(models.AbstractModel):
    _inherit = 'base'

    def check_access_rule(self, operation):
        try:
            return super().check_access_rule(operation)
        except AccessError as original_error:
            if self.env.su or operation != 'read':
                raise original_error
            if self.env.context.get('soft_restrict_skip'):
                raise original_error
            if not self:
                raise original_error

            try:
                if self._soft_restrict_can_read_denied_records():
                    return None
            except Exception:
                _logger.exception('Soft Restrict failed safely on model %s ids %s', self._name, self.ids)

            raise original_error

    def _soft_restrict_can_read_denied_records(self):
        configs = self.env['soft.restrict.config']._get_active_configs_for_model(self._name)
        if not configs:
            return False

        user = self.env.user
        for config in configs:
            if config.group_id and user not in config.group_id.users:
                continue
            if all(record.sudo()._soft_restrict_record_allowed(config, user) for record in self):
                return True
        return False

    def _soft_restrict_record_allowed(self, config, user):
        self.ensure_one()
        sudo_record = self.sudo()

        # Owner fields: allow if the denied record itself belongs to the user.
        for fname in config._valid_owner_fields():
            owner = sudo_record[fname]
            if owner and owner.id == user.id:
                return True

        # Related records: allow only if standard Odoo access permits reading the related record.
        for fname in config._valid_link_fields():
            related_records = sudo_record[fname]
            if not related_records:
                continue

            for related in related_records.exists():
                try:
                    related_user_record = related.with_user(user).with_context(soft_restrict_skip=True)
                    related_user_record.check_access_rights('read')
                    related_user_record.check_access_rule('read')
                    return True
                except AccessError:
                    continue
        return False
