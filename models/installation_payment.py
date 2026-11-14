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

    def _wof_user_payment_settings(self):
        """The user's customer-payment journal settings for the order's branch
        (yousentech_invoicing_payment_journal), when that module is installed."""
        company = self.company_id or self.env.company
        user = self.env.user
        if 'journals_ids' not in user._fields:
            return None
        return user.journals_ids.filtered(
            lambda rec: rec.company_id == company and rec.journal_type == 'payment_customer')

    def _wof_allowed_payment_journals(self):
        """Bank / cash journals the user may receive on: the journals allowed in the
        user's payment settings when defined, else every bank / cash journal of the
        branch (the accounting access rules still apply)."""
        self.ensure_one()
        company = self.company_id or self.env.company
        journals = self.env['account.journal'].search([
            ('type', 'in', ('bank', 'cash')), ('company_id', '=', company.id)])
        settings = self._wof_user_payment_settings()
        if settings:
            allowed = self.env['account.journal']
            for name in ('journal_ids', 'allowed_journal_ids', 'default_journal_id'):
                if name in settings._fields:
                    allowed |= settings.mapped(name)
            if allowed:
                journals &= allowed
        return journals

    def _wof_default_payment_journal(self):
        """User's default customer payment journal, else the company's, else the first allowed."""
        self.ensure_one()
        company = self.company_id or self.env.company
        allowed = self._wof_allowed_payment_journals()
        settings = self._wof_user_payment_settings()
        if settings and 'default_journal_id' in settings._fields:
            journal = settings.mapped('default_journal_id')[:1]
            if journal and journal in allowed:
                return journal
        if 'payment_sale_journal_id' in company._fields and company.payment_sale_journal_id \
                and company.payment_sale_journal_id in allowed:
            return company.payment_sale_journal_id
        return allowed[:1]

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
    amount_paid = fields.Monetary(related='order_id.amount_paid', string='المدفوع')
    amount = fields.Monetary(string='المبلغ')
    allowed_journal_ids = fields.Many2many('account.journal', compute='_compute_allowed_journals')
    journal_id = fields.Many2one(
        'account.journal', string='طريقة الدفع',
        domain="[('id', 'in', allowed_journal_ids)]",
    )
    split = fields.Boolean(string='الدفع بأكثر من طريقة')
    line_ids = fields.One2many('wof.order.payment.wizard.line', 'wizard_id', string='طرق الدفع')
    lines_total = fields.Monetary(string='مجموع الدفعات', compute='_compute_totals')
    remaining_after = fields.Monetary(string='المتبقي بعد الدفع', compute='_compute_totals')

    @api.depends('order_id')
    def _compute_allowed_journals(self):
        for wizard in self:
            wizard.allowed_journal_ids = wizard.order_id._wof_allowed_payment_journals() if wizard.order_id else False

    @api.depends('split', 'amount', 'line_ids.amount', 'payment_type', 'amount_residual', 'amount_to_refund')
    def _compute_totals(self):
        for wizard in self:
            total = sum(wizard.line_ids.mapped('amount')) if wizard.split else (wizard.amount or 0.0)
            base = wizard.amount_to_refund if wizard.payment_type == 'outbound' else wizard.amount_residual
            wizard.lines_total = total
            wizard.remaining_after = max((base or 0.0) - total, 0.0)

    @api.onchange('split')
    def _onchange_split(self):
        if self.split and not self.line_ids:
            self.line_ids = [(0, 0, {'journal_id': self.journal_id.id, 'amount': self.amount})]
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

    def _wof_payment_parts(self):
        """[(journal, amount, memo)] to post: the split lines, else the single payment."""
        if self.split:
            if not self.env.user.has_group('yousentech_wo_v4.group_wo_split_payment'):
                raise ValidationError(_('الدفع بأكثر من طريقة يحتاج صلاحية «دفع متعدد في أمر التركيب».'))
            parts = [(line.journal_id, line.amount, line.memo) for line in self.line_ids if line.amount]
            if not parts:
                raise ValidationError(_('أضف طريقة دفع واحدة على الأقل بمبلغ.'))
            return parts
        return [(self.journal_id, self.amount, self.memo)]

    def action_confirm(self):
        self.ensure_one()
        order = self.order_id
        currency = order.currency_id or order.company_id.currency_id
        parts = self._wof_payment_parts()
        allowed = order._wof_allowed_payment_journals()
        total = 0.0
        for journal, amount, _memo in parts:
            if not journal:
                raise ValidationError(_('اختر طريقة الدفع.'))
            if journal not in allowed:
                raise ValidationError(_('طريقة الدفع «%s» غير مسموحة لك في هذا الفرع.') % journal.display_name)
            if float_compare(amount or 0.0, 0.0, precision_rounding=currency.rounding) <= 0:
                raise ValidationError(_('أدخل مبلغًا أكبر من صفر.'))
            total += amount
        outbound = self.payment_type == 'outbound'
        if outbound:
            if float_compare(total, order.finance_to_refund, precision_rounding=currency.rounding) > 0:
                raise ValidationError(_('المبلغ أكبر من المتبقي للرد (%s).') % order.finance_to_refund)
        elif float_compare(total, order.amount_residual, precision_rounding=currency.rounding) > 0:
            raise ValidationError(_('المبلغ أكبر من المتبقي على الأمر (%s).') % order.amount_residual)
        payments = self.env['account.payment']
        for journal, amount, memo in parts:
            payment = self.env['account.payment'].create({
                'payment_type': self.payment_type,
                'partner_type': 'customer',
                'partner_id': order.partner_id.commercial_partner_id.id,
                'amount': amount,
                'currency_id': currency.id,
                'journal_id': journal.id,
                'date': self.date,
                'ref': ' - '.join(filter(None, [order.name, memo])),
                'company_id': order.company_id.id,
                'wof_order_id': order.id,
            })
            payment.action_post()
            payments |= payment
        payment = payments
        journals_text = '، '.join(payments.journal_id.mapped('name'))
        if outbound:
            for refund in order._wof_finance_moves().filtered(
                    lambda move: move.move_type == 'out_refund' and move.state == 'posted'):
                order._wof_reconcile_refunds(refund)
            order._log_business_event('order.payment_refunded', details={
                'amount': total, 'journal': journals_text,
                'payment': '، '.join(payment.mapped('name')),
            })
            return {'type': 'ir.actions.act_window_close'}
        if order.invoice_id and order.invoice_id.state == 'posted':
            order._wof_reconcile_payments(order.invoice_id)
        order._log_business_event('order.payment_registered', details={
            'amount': total, 'journal': journals_text,
            'payment': '، '.join(payment.mapped('name')),
        })
        order._wof_after_payment()
        return {'type': 'ir.actions.act_window_close'}


class WofOrderPaymentWizardLine(models.TransientModel):
    _name = 'wof.order.payment.wizard.line'
    _description = 'طريقة دفع في تسجيل دفعة أمر التركيب'

    wizard_id = fields.Many2one('wof.order.payment.wizard', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='wizard_id.currency_id')
    allowed_journal_ids = fields.Many2many(related='wizard_id.allowed_journal_ids')
    journal_id = fields.Many2one('account.journal', string='طريقة الدفع', required=True,
                                 domain="[('id', 'in', allowed_journal_ids)]")
    amount = fields.Monetary(string='المبلغ')
    memo = fields.Char(string='ملاحظة')
