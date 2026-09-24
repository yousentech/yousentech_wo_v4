# -*- coding: utf-8 -*-

import re

from odoo import fields, models, _
from odoo.exceptions import ValidationError


class WofSetupSizeDialog(models.TransientModel):
    _name = 'wof.setup.size.dialog'
    _description = 'نافذة إضافة وتعديل حجم سيارة في التهيئة'

    mode = fields.Selection(
        [('add', 'إضافة'), ('edit', 'تعديل')], required=True, default='add', readonly=True,
    )
    profile_id = fields.Many2one(
        'wof.company.profile', string='ملف التهيئة', required=True, readonly=True,
    )
    size_line_id = fields.Many2one(
        'wof.setup.size.line', string='حجم السيارة', readonly=True,
    )
    name = fields.Char(string='اسم حجم السيارة')

    def _dialog_action(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('تعديل حجم السيارة') if self.mode == 'edit' else _('إضافة حجم سيارة'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('yousentech_wo_v4.view_wof_setup_size_dialog_form').id,
            'target': 'new',
        }

    def _new_code(self, name):
        base = re.sub(r'[^A-Z0-9]+', '_', (name or '').upper()).strip('_')
        if not base:
            base = 'SIZE'
        base = ('CUSTOM_' + base)[:48]
        code = base
        index = 2
        existing = set(self.profile_id.size_line_ids.mapped('code'))
        while code in existing:
            code = f'{base[:42]}_{index}'
            index += 1
        return code

    def action_confirm(self):
        self.ensure_one()
        self.profile_id._ensure_can_configure()
        name = (self.name or '').strip()
        if not name:
            raise ValidationError(_('اسم حجم السيارة مطلوب.'))

        duplicate_domain = [
            ('profile_id', '=', self.profile_id.id),
            ('name', '=ilike', name),
        ]
        if self.size_line_id:
            duplicate_domain.append(('id', '!=', self.size_line_id.id))
        if self.env['wof.setup.size.line'].search_count(duplicate_domain):
            raise ValidationError(_('اسم حجم السيارة مستخدم مسبقًا في مركز التهيئة.'))

        if self.mode == 'edit':
            if not self.size_line_id or self.size_line_id.profile_id != self.profile_id:
                raise ValidationError(_('تعذر العثور على حجم السيارة المطلوب تعديله.'))
            self.size_line_id.write({'name': name})
        else:
            sequence = max(self.profile_id.size_line_ids.mapped('sequence') or [0]) + 10
            self.env['wof.setup.size.line'].create({
                'profile_id': self.profile_id.id,
                'sequence': sequence,
                'code': self._new_code(name),
                'name': name,
                'selected': True,
                'is_system_default': False,
            })
        return self.profile_id._wizard_action()

    def action_cancel(self):
        self.ensure_one()
        if not self.profile_id:
            return {'type': 'ir.actions.act_window_close'}
        return self.profile_id._wizard_action()
