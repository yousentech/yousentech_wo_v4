# -*- coding: utf-8 -*-

from odoo import fields, models, _
from odoo.exceptions import ValidationError


class WofSetupTintDialog(models.TransientModel):
    _name = 'wof.setup.tint.dialog'
    _description = 'نافذة تعديل اسم درجة اللون في التهيئة'

    profile_id = fields.Many2one(
        'wof.company.profile', string='ملف التهيئة', required=True, readonly=True,
    )
    tint_line_id = fields.Many2one(
        'wof.setup.tint.shade.line', string='درجة اللون', required=True, readonly=True,
    )
    name = fields.Char(string='اسم درجة اللون', required=True)

    def _dialog_action(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('تعديل درجة اللون'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('yousentech_wo_v4.view_wof_setup_tint_dialog_form').id,
            'target': 'new',
        }

    def action_confirm(self):
        self.ensure_one()
        self.profile_id._ensure_can_configure()
        name = (self.name or '').strip()
        if not name:
            raise ValidationError(_('اسم درجة اللون مطلوب.'))
        if not self.tint_line_id or self.tint_line_id.profile_id != self.profile_id:
            raise ValidationError(_('تعذر العثور على درجة اللون المطلوب تعديلها.'))
        duplicate = self.env['wof.setup.tint.shade.line'].search_count([
            ('profile_id', '=', self.profile_id.id),
            ('value', '=ilike', name),
            ('id', '!=', self.tint_line_id.id),
        ])
        if duplicate:
            raise ValidationError(_('اسم درجة اللون مستخدم مسبقًا في مركز التهيئة.'))
        official_duplicate = self.env['wof.tint.degree'].with_context(active_test=False).search_count([
            ('company_id', '=', self.profile_id.company_id.id),
            ('value', '=ilike', name),
            ('code', '!=', self.tint_line_id.code),
        ])
        if official_duplicate:
            raise ValidationError(_('اسم درجة اللون مستخدم مسبقًا ضمن درجات المركز الرسمية.'))
        self.tint_line_id.write({'value': name})
        return self.profile_id._wizard_action()

    def action_cancel(self):
        self.ensure_one()
        return self.profile_id._wizard_action() if self.profile_id else {'type': 'ir.actions.act_window_close'}
