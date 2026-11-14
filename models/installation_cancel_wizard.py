# -*- coding: utf-8 -*-
"""«إلغاء الأمر»: a dialog asks for the reason, then cancels with the usual checks."""

from odoo import fields, models, _
from odoo.exceptions import ValidationError


class WofCancelWizard(models.TransientModel):
    _name = 'wof.order.cancel.wizard'
    _description = 'إلغاء أمر التركيب'

    order_id = fields.Many2one('wof.installation.order', string='أمر التركيب', required=True, readonly=True)
    order_state = fields.Selection(related='order_id.state', string='حالة الأمر')
    reason = fields.Text(string='سبب الإلغاء', required=True)

    def action_confirm(self):
        self.ensure_one()
        reason = (self.reason or '').strip()
        if not reason:
            raise ValidationError(_('اكتب سبب الإلغاء.'))
        order = self.order_id
        order.write({'cancellation_reason': reason})
        order.action_cancel()
        return {'type': 'ir.actions.act_window_close'}


class WofOrderCancelDialog(models.Model):
    _inherit = 'wof.installation.order'

    def action_open_cancel_wizard(self):
        self.ensure_one()
        self._ensure_role('yousentech_wo_v4.group_wo_supervisor', 'yousentech_wo_v4.group_wo_manager')
        if self.state == 'cancelled':
            raise ValidationError(_('الأمر ملغي مسبقًا.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('إلغاء الأمر (مرتجع)') if self.state == 'delivered' else _('إلغاء الأمر'),
            'res_model': 'wof.order.cancel.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id, 'default_reason': self.cancellation_reason or False},
        }
