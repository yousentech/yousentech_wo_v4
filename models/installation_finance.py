# -*- coding: utf-8 -*-
"""Financial follow-up of an installation order: invoices, credit notes,
payments received and amounts paid back.

The figures read the order's accounting documents (its sale order invoices,
their credit notes and the payments linked or matched to them). Before any
invoice is posted the order total is what the customer owes, so an advance
payment shows as collected, not as money to give back.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero

FINANCE_STATES = [
    ('none', 'لا حركة مالية'),
    ('due', 'متبقٍ للتحصيل'),
    ('settled', 'مسدد'),
    ('refund', 'متبقٍ للرد'),
]


class AccountMoveWofRefund(models.Model):
    _inherit = 'account.move'

    @api.model_create_multi
    def create(self, vals_list):
        # A credit note made from an order invoice stays linked to the order.
        for vals in vals_list:
            if vals.get('reversed_entry_id') and not vals.get('wof_order_id'):
                origin = self.browse(vals['reversed_entry_id'])
                if origin.wof_order_id:
                    vals['wof_order_id'] = origin.wof_order_id.id
        return super().create(vals_list)

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        for move in posted.filtered(lambda rec: rec.wof_order_id and rec.move_type == 'out_refund'):
            move.wof_order_id._wof_reconcile_refunds(move)
        return posted


class WofInstallationOrderFinance(models.Model):
    _inherit = 'wof.installation.order'

    finance_move_ids = fields.Many2many(
        'account.move', compute='_compute_wof_finance', string='الفواتير والإشعارات الدائنة')
    finance_payment_ids = fields.Many2many(
        'account.payment', compute='_compute_wof_finance', string='حركات الدفع')
    finance_invoiced = fields.Monetary(string='إجمالي الفواتير', compute='_compute_wof_finance')
    finance_credited = fields.Monetary(string='الإشعارات الدائنة', compute='_compute_wof_finance')
    finance_received = fields.Monetary(string='المقبوض', compute='_compute_wof_finance')
    finance_refunded = fields.Monetary(string='المردود للعميل', compute='_compute_wof_finance')
    finance_due = fields.Monetary(string='المتبقي للتحصيل', compute='_compute_wof_finance')
    finance_to_refund = fields.Monetary(string='المتبقي للرد', compute='_compute_wof_finance')
    finance_state = fields.Selection(FINANCE_STATES, string='الحالة المالية', compute='_compute_wof_finance')
    finance_draft_count = fields.Integer(compute='_compute_wof_finance')
    finance_access = fields.Boolean(compute='_compute_wof_finance')

    # ------------------------------------------------------------ documents
    def _wof_finance_moves(self):
        self.ensure_one()
        Move = self.env['account.move']
        moves = Move.search([('wof_order_id', '=', self.id), ('move_type', 'in', ('out_invoice', 'out_refund'))]) \
            if self.id else Move
        moves |= self.sale_order_id.invoice_ids.filtered(lambda move: move.move_type in ('out_invoice', 'out_refund'))
        invoices = moves.filtered(lambda move: move.move_type == 'out_invoice')
        if invoices:
            moves |= Move.search([('reversed_entry_id', 'in', invoices.ids), ('move_type', '=', 'out_refund')])
        return moves

    def _wof_finance_payments(self, posted_moves):
        self.ensure_one()
        payments = self.payment_ids
        for move in posted_moves:
            payments |= move._get_reconciled_payments()
        return payments.filtered(lambda pay: pay.state == 'posted' and pay.company_id == self.company_id)

    def _wof_amount(self, payment):
        currency = self.currency_id or self.company_id.currency_id
        return payment.currency_id._convert(payment.amount, currency, self.company_id, payment.date)

    @api.depends('payment_ids.state', 'payment_ids.amount', 'sale_order_id.invoice_ids.state',
                 'invoice_id.state', 'amount_total', 'state')
    def _compute_wof_finance(self):
        readable = self.env['account.move'].check_access_rights('read', raise_exception=False) \
            and self.env['account.payment'].check_access_rights('read', raise_exception=False)
        for order in self:
            currency = order.currency_id or order.company_id.currency_id
            values = {
                'finance_move_ids': [(6, 0, [])], 'finance_payment_ids': [(6, 0, [])],
                'finance_invoiced': 0.0, 'finance_credited': 0.0, 'finance_received': 0.0,
                'finance_refunded': 0.0, 'finance_due': 0.0, 'finance_to_refund': 0.0,
                'finance_state': 'none', 'finance_draft_count': 0, 'finance_access': bool(readable),
            }
            if not readable or not order.id:
                order.update(values)
                continue
            moves = order._wof_finance_moves()
            posted = moves.filtered(lambda move: move.state == 'posted')
            payments = order._wof_finance_payments(posted)
            invoiced = sum(posted.filtered(lambda move: move.move_type == 'out_invoice').mapped('amount_total'))
            credited = sum(posted.filtered(lambda move: move.move_type == 'out_refund').mapped('amount_total'))
            received = sum(order._wof_amount(pay) for pay in payments.filtered(lambda pay: pay.payment_type == 'inbound'))
            refunded = sum(order._wof_amount(pay) for pay in payments.filtered(lambda pay: pay.payment_type == 'outbound'))
            if posted.filtered(lambda move: move.move_type == 'out_invoice'):
                owed = invoiced - credited
            else:
                owed = 0.0 if order.state == 'cancelled' else order.amount_total
            balance = owed - (received - refunded)
            if float_is_zero(balance, precision_rounding=currency.rounding):
                state = 'settled' if (posted or payments) else 'none'
            elif balance > 0:
                state = 'due' if (posted or payments) else 'none'
            else:
                state = 'refund'
            values.update({
                'finance_move_ids': [(6, 0, moves.ids)], 'finance_payment_ids': [(6, 0, payments.ids)],
                'finance_invoiced': invoiced, 'finance_credited': credited,
                'finance_received': received, 'finance_refunded': refunded,
                'finance_due': max(balance, 0.0), 'finance_to_refund': max(-balance, 0.0),
                'finance_state': state,
                'finance_draft_count': len(moves.filtered(lambda move: move.state == 'draft')),
            })
            order.update(values)

    # ------------------------------------------------------------- matching
    def _wof_reconcile_refunds(self, refund):
        """Match money paid back to the customer with a posted credit note."""
        self.ensure_one()
        if refund.state != 'posted':
            return
        receivable = refund.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable' and not line.reconciled)
        for payment in self.payment_ids.filtered(lambda pay: pay.state == 'posted' and pay.payment_type == 'outbound'):
            if not receivable:
                break
            lines = payment.move_id.line_ids.filtered(
                lambda line: line.account_id == receivable[0].account_id and not line.reconciled)
            if lines:
                (lines + receivable).reconcile()
                receivable = receivable.filtered(lambda line: not line.reconciled)

    # -------------------------------------------------------------- actions
    def action_wof_credit_note(self):
        """Credit note (إشعار دائن) for the order's posted invoices, through Odoo's reversal wizard."""
        self.ensure_one()
        if not self.env['account.move.reversal'].check_access_rights('create', raise_exception=False):
            raise UserError(_('لا تملك صلاحية إصدار الإشعارات الدائنة. اطلب صلاحية «الفوترة» من مسؤول النظام.'))
        invoices = self._wof_finance_moves().filtered(
            lambda move: move.move_type == 'out_invoice' and move.state == 'posted')
        if not invoices:
            raise ValidationError(_('لا توجد فاتورة مرحلة لإصدار إشعار دائن عليها.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('إشعار دائن لأمر التركيب'),
            'res_model': 'account.move.reversal',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_model': 'account.move', 'active_ids': invoices.ids,
                'default_reason': _('مرتجع أمر التركيب %s') % self.name,
            },
        }

    def action_wof_refund_payment(self):
        """Pay money back to the customer (outbound payment linked to the order)."""
        self.ensure_one()
        if not self.env['account.payment'].check_access_rights('create', raise_exception=False):
            raise UserError(_('لا تملك صلاحية تسجيل الدفعات. اطلب صلاحية «الفوترة» من مسؤول النظام.'))
        if self.finance_to_refund <= 0:
            raise ValidationError(_('لا يوجد مبلغ مستحق الرد للعميل في هذا الأمر.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('رد مبلغ للعميل'),
            'res_model': 'wof.order.payment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id, 'default_payment_type': 'outbound'},
        }

    def action_wof_view_finance_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('فواتير وإشعارات أمر التركيب'),
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self._wof_finance_moves().ids)],
            'context': {'create': False},
        }

    # ------------------------------------------------------------ cancelling
    def _wof_stock_net_delivered(self):
        """Quantity per product delivered to the customer and not returned."""
        self.ensure_one()
        net = {}
        for move in self.sale_order_id.picking_ids.move_ids.filtered(lambda rec: rec.state == 'done'):
            sign = 1 if move.location_dest_id.usage == 'customer' else -1 if move.location_id.usage == 'customer' else 0
            if sign:
                net[move.product_id] = net.get(move.product_id, 0.0) + sign * move.quantity
        return {product: qty for product, qty in net.items()
                if float_compare(qty, 0.0, precision_rounding=product.uom_id.rounding) > 0}

    def _wof_check_finance_before_cancel(self):
        self.ensure_one()
        currency = self.currency_id or self.company_id.currency_id
        if not self.finance_access:
            return
        if self.finance_draft_count:
            raise ValidationError(_('توجد فاتورة أو إشعار دائن مسودة. رحّله أو ألغه قبل إلغاء الأمر.'))
        if not float_is_zero(self.finance_invoiced - self.finance_credited, precision_rounding=currency.rounding):
            raise ValidationError(_('أصدر إشعارًا دائنًا بكامل الفاتورة قبل إلغاء الأمر (الصافي المفوتر %s).')
                                  % (self.finance_invoiced - self.finance_credited))
        if not float_is_zero(self.finance_received - self.finance_refunded, precision_rounding=currency.rounding):
            raise ValidationError(_('رد المبالغ المقبوضة للعميل قبل إلغاء الأمر (المتبقي للرد %s).')
                                  % (self.finance_received - self.finance_refunded))
        delivered = self._wof_stock_net_delivered()
        if delivered:
            raise ValidationError(_('يوجد صرف مخزني لم يُرجَع: %s. أنشئ مرتجعًا من الشحنة أولًا.')
                                  % '، '.join(product.display_name for product in delivered))
