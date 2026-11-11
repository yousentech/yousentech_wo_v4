# -*- coding: utf-8 -*-
"""Payments recorded on the installation order (advance or collection).

A payment is a normal customer payment (account.payment) linked to the order. It
is matched with the order's invoice once the invoice is posted. The payment
journal follows the user's default customer payment journal, else the
company's, when yousentech_invoicing_payment_journal is installed; otherwise the
first bank or cash journal.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    wof_order_id = fields.Many2one(
        'wof.installation.order', string='أمر التركيب', index=True, copy=False, ondelete='restrict',
    )


class WofInstallationOrderPayment(models.Model):
    _inherit = 'wof.installation.order'

    payment_ids = fields.One2many('account.payment', 'wof_order_id', string='الدفعات', readonly=True)
    payment_count = fields.Integer(compute='_compute_wof_payments')
    amount_paid = fields.Monetary(string='المدفوع', compute='_compute_wof_payments')
    amount_residual = fields.Monetary(string='المتبقي', compute='_compute_wof_payments')
    payment_status = fields.Selection(
        [('not_paid', 'غير مدفوع'), ('partial', 'مدفوع جزئيًا'), ('paid', 'مدفوع بالكامل')],
        string='حالة الدفع', compute='_compute_wof_payments',
    )

    @api.depends('payment_ids.state', 'payment_ids.amount', 'payment_ids.payment_type', 'amount_total')
    def _compute_wof_payments(self):
        # Users without accounting rights still open the order: they see the total as remaining.
        readable = self.env['account.payment'].check_access_rights('read', raise_exception=False)
        for order in self:
            posted = order.payment_ids.filtered(lambda pay: pay.state == 'posted') if readable \
                else self.env['account.payment']
            paid = sum(posted.filtered(lambda pay: pay.payment_type == 'inbound').mapped('amount')) \
                - sum(posted.filtered(lambda pay: pay.payment_type == 'outbound').mapped('amount'))
            currency = order.currency_id or order.company_id.currency_id
            order.payment_count = len(order.payment_ids) if readable else 0
            order.amount_paid = paid
            order.amount_residual = max(order.amount_total - paid, 0.0)
            if float_is_zero(paid, precision_rounding=currency.rounding):
                order.payment_status = 'not_paid'
            elif float_compare(paid, order.amount_total, precision_rounding=currency.rounding) >= 0:
                order.payment_status = 'paid'
            else:
                order.payment_status = 'partial'

    def _wof_after_payment(self):
        """Hook: what follows a recorded payment (see the invoicing flow)."""
        return True

    def _wof_is_fully_paid(self):
        self.ensure_one()
        return self.amount_total > 0 and self.payment_status == 'paid'

    def _wof_default_payment_journal(self):
        """User's default customer payment journal, else the company's, else the first bank/cash."""
        self.ensure_one()
        company = self.company_id or self.env.company
        user = self.env.user
        if 'journals_ids' in user._fields:
            journal = user.journals_ids.filtered(
                lambda rec: rec.company_id == company and rec.journal_type == 'payment_customer'
            ).mapped('default_journal_id')[:1]
            if journal:
                return journal
        if 'payment_sale_journal_id' in company._fields and company.payment_sale_journal_id:
            return company.payment_sale_journal_id
        return self.env['account.journal'].search([
            ('type', 'in', ('bank', 'cash')), ('company_id', '=', company.id),
        ], limit=1)

    def action_register_payment(self):
        self.ensure_one()
        if self.state == 'cancelled':
            raise ValidationError(_('لا يمكن تسجيل دفعة على أمر ملغي.'))
        if not self.env['account.payment'].check_access_rights('create', raise_exception=False):
            raise UserError(_('لا تملك صلاحية تسجيل الدفعات. اطلب صلاحية «الفوترة» من مسؤول النظام.'))
        if self.amount_residual <= 0:
            raise ValidationError(_('الأمر مدفوع بالكامل.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('تسجيل دفعة'),
            'res_model': 'wof.order.payment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }

    def action_view_payments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('دفعات أمر التركيب'),
            'res_model': 'account.payment',
            'view_mode': 'tree,form',
            'domain': [('wof_order_id', '=', self.id)],
            'context': {'create': False},
        }

    def _wof_reconcile_payments(self, invoice):
        """Match the order's posted payments with its posted invoice."""
        self.ensure_one()
        if invoice.state != 'posted':
            return
        receivable = invoice.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable' and not line.reconciled)
        if not receivable:
            return
        for payment in self.payment_ids.filtered(lambda pay: pay.state == 'posted' and pay.payment_type == 'inbound'):
            lines = payment.move_id.line_ids.filtered(
                lambda line: line.account_id == receivable[0].account_id and not line.reconciled)
            if lines:
                (lines + receivable).reconcile()
                receivable = receivable.filtered(lambda line: not line.reconciled)
                if not receivable:
                    break


class WofOrderPaymentWizard(models.TransientModel):
    _name = 'wof.order.payment.wizard'
    _description = 'تسجيل دفعة على أمر التركيب'

    order_id = fields.Many2one('wof.installation.order', string='أمر التركيب', required=True, readonly=True)
    partner_id = fields.Many2one(related='order_id.partner_id')
    currency_id = fields.Many2one(related='order_id.currency_id')
    amount_total = fields.Monetary(related='order_id.amount_total', string='إجمالي الأمر')
    amount_residual = fields.Monetary(related='order_id.amount_residual', string='المتبقي')
    payment_type = fields.Selection(
        [('inbound', 'قبض من العميل'), ('outbound', 'رد مبلغ للعميل')],
        string='نوع الحركة', required=True, default='inbound', readonly=True,
    )
    amount_to_refund = fields.Monetary(related='order_id.finance_to_refund', string='المتبقي للرد')
    amount = fields.Monetary(string='المبلغ', required=True)
    journal_id = fields.Many2one(
        'account.journal', string='طريقة الدفع', required=True,
        domain="[('type', 'in', ('bank', 'cash'))]",
    )
    date = fields.Date(string='التاريخ', required=True, default=fields.Date.context_today)
    memo = fields.Char(string='ملاحظة')

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        order = self.env['wof.installation.order'].browse(values.get('order_id') or self.env.context.get('default_order_id'))
        if order:
            outbound = (values.get('payment_type') or self.env.context.get('default_payment_type')) == 'outbound'
            values.setdefault('amount', order.finance_to_refund if outbound else order.amount_residual)
            journal = order._wof_default_payment_journal()
            if journal:
                values.setdefault('journal_id', journal.id)
        return values

    def action_confirm(self):
        self.ensure_one()
        order = self.order_id
        currency = order.currency_id or order.company_id.currency_id
        if float_compare(self.amount, 0.0, precision_rounding=currency.rounding) <= 0:
            raise ValidationError(_('أدخل مبلغًا أكبر من صفر.'))
        outbound = self.payment_type == 'outbound'
        if outbound:
            if float_compare(self.amount, order.finance_to_refund, precision_rounding=currency.rounding) > 0:
                raise ValidationError(_('المبلغ أكبر من المتبقي للرد (%s).') % order.finance_to_refund)
        elif float_compare(self.amount, order.amount_residual, precision_rounding=currency.rounding) > 0:
            raise ValidationError(_('المبلغ أكبر من المتبقي على الأمر (%s).') % order.amount_residual)
        payment = self.env['account.payment'].create({
            'payment_type': self.payment_type,
            'partner_type': 'customer',
            'partner_id': order.partner_id.commercial_partner_id.id,
            'amount': self.amount,
            'currency_id': currency.id,
            'journal_id': self.journal_id.id,
            'date': self.date,
            'ref': ' - '.join(filter(None, [order.name, self.memo])),
            'company_id': order.company_id.id,
            'wof_order_id': order.id,
        })
        payment.action_post()
        if outbound:
            for refund in order._wof_finance_moves().filtered(
                    lambda move: move.move_type == 'out_refund' and move.state == 'posted'):
                order._wof_reconcile_refunds(refund)
            order._log_business_event('order.payment_refunded', details={
                'amount': self.amount, 'journal': self.journal_id.name, 'payment': payment.name,
            })
            return {'type': 'ir.actions.act_window_close'}
        if order.invoice_id and order.invoice_id.state == 'posted':
            order._wof_reconcile_payments(order.invoice_id)
        order._log_business_event('order.payment_registered', details={
            'amount': self.amount, 'journal': self.journal_id.name, 'payment': payment.name,
        })
        order._wof_after_payment()
        return {'type': 'ir.actions.act_window_close'}
