# -*- coding: utf-8 -*-
"""Delivery of a car that still owes money: block, warn or allow (setup choice).

Credit customers are always exempt: their balance stays on their account.
"""

from odoo import fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools import float_is_zero
from odoo.tools.misc import formatLang


class WofOrderDeliveryPolicy(models.Model):
    _inherit = 'wof.installation.order'

    def _wof_is_credit_customer(self):
        self.ensure_one()
        partner = self.partner_id.commercial_partner_id
        return 'pay_type' in partner._fields and partner.pay_type == 'credit'

    def _wof_delivery_unpaid_policy(self):
        """'allow' | 'warn' | 'block' for this order right now."""
        self.ensure_one()
        currency = self.currency_id or self.company_id.currency_id
        if float_is_zero(self.amount_residual, precision_rounding=currency.rounding) or self.amount_residual < 0:
            return 'allow'
        if self._wof_is_credit_customer():
            return 'allow'
        profile = self.env['wof.company.profile']._wof_get_profile()
        return profile.delivery_unpaid_policy if profile and profile.delivery_unpaid_policy else 'block'

    def _wof_residual_text(self):
        self.ensure_one()
        return formatLang(self.env, self.amount_residual, currency_obj=self.currency_id or self.company_id.currency_id)

    def action_deliver(self):
        self.ensure_one()
        if self.state == 'ready' and not self.env.context.get('wof_deliver_unpaid_ok'):
            policy = self._wof_delivery_unpaid_policy()
            if policy == 'block':
                raise ValidationError(_(
                    'لا يمكن تسليم السيارة: على الأمر مبلغ متبقٍ %s. سجّل الدفعة أولًا ثم سلّم السيارة.'
                ) % self._wof_residual_text())
            if policy == 'warn':
                return {
                    'type': 'ir.actions.act_window',
                    'name': _('تسليم سيارة عليها مبلغ متبقٍ'),
                    'res_model': 'wof.order.deliver.wizard',
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {'default_order_id': self.id},
                }
        return super().action_deliver()


class WofDeliverWizard(models.TransientModel):
    _name = 'wof.order.deliver.wizard'
    _description = 'تأكيد تسليم سيارة عليها مبلغ متبقٍ'

    order_id = fields.Many2one('wof.installation.order', string='أمر التركيب', required=True, readonly=True)
    currency_id = fields.Many2one(related='order_id.currency_id')
    amount_total = fields.Monetary(related='order_id.amount_total', string='الإجمالي')
    amount_paid = fields.Monetary(related='order_id.amount_paid', string='المدفوع')
    amount_residual = fields.Monetary(related='order_id.amount_residual', string='المتبقي')

    def action_confirm(self):
        self.ensure_one()
        order = self.order_id
        residual = order._wof_residual_text()
        result = order.with_context(wof_deliver_unpaid_ok=True).action_deliver()
        order.message_post(body=_('سُلِّمت السيارة وعلى الأمر مبلغ متبقٍ %s، بتأكيد %s.') % (residual, self.env.user.name))
        return result if isinstance(result, dict) else {'type': 'ir.actions.act_window_close'}

    def action_register_payment(self):
        self.ensure_one()
        return self.order_id.action_register_payment()
