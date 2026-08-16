# -*- coding: utf-8 -*-

from odoo import fields, models, _
from odoo.exceptions import ValidationError


class WofSetupActivityDialog(models.TransientModel):
    _name = 'wof.setup.activity.dialog'
    _description = 'نافذة إضافة وتعديل نشاط التهيئة'

    mode = fields.Selection(
        [('add', 'إضافة'), ('edit', 'تعديل')], required=True, default='add', readonly=True,
    )
    profile_id = fields.Many2one(
        'wof.company.profile', string='ملف التهيئة', required=True, readonly=True,
    )
    activity_line_id = fields.Many2one(
        'wof.setup.activity.line', string='النشاط', readonly=True,
    )
    name = fields.Char(string='اسم النشاط')
    description = fields.Text(string='ملاحظات')

    def _dialog_action(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('تعديل النشاط') if self.mode == 'edit' else _('إضافة نشاط'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref(
                'yousentech_wo_v4.view_wof_setup_activity_dialog_form'
            ).id,
            'target': 'new',
        }

    def action_confirm(self):
        self.ensure_one()
        self.profile_id._ensure_can_configure()
        name = (self.name or '').strip()
        if not name:
            raise ValidationError(_('اسم النشاط مطلوب.'))
        duplicate_domain = [
            ('profile_id', '=', self.profile_id.id),
            ('name', '=ilike', name),
        ]
        if self.activity_line_id:
            duplicate_domain.append(('id', '!=', self.activity_line_id.id))
        if self.env['wof.setup.activity.line'].search_count(duplicate_domain):
            raise ValidationError(_('اسم النشاط مستخدم مسبقًا في مركز التهيئة.'))

        description = (self.description or '').strip() or False
        if self.mode == 'edit':
            if not self.activity_line_id or self.activity_line_id.profile_id != self.profile_id:
                raise ValidationError(_('تعذر العثور على النشاط المطلوب تعديله.'))
            self.activity_line_id.write({
                'name': name,
                'description': description,
            })
        else:
            sequence = max(self.profile_id.activity_line_ids.mapped('sequence') or [0]) + 10
            self.env['wof.setup.activity.line'].create({
                'profile_id': self.profile_id.id,
                'sequence': sequence,
                'activity_type': 'general',
                'name': name,
                # New activities must never receive an automatic description.
                'description': description,
                'selected': True,
                'is_system_default': False,
            })

        # Re-open the same Stage 1 wizard so the card grid is refreshed immediately.
        return self.profile_id._wizard_action()

