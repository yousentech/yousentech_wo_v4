# -*- coding: utf-8 -*-
"""Sale order, delivery and invoice from an installation order.

Installation order -> confirmed sale order -> delivery (stock) -> draft invoice.

Sale order lines:
* one line per service, with the component's product (part or service area),
  its price and discount (net or visible, per the setup);
* a note line under it: "film · grade" and the film's description;
* one line per stock product (film roll, recorded materials) at price zero, so
  the delivery takes it out of stock. These lines never reach the invoice.

When the invoice is created follows the setup: manually, when the order is
confirmed, after full payment, or by the customer's dealing type (credit at
confirmation, cash after full payment; read from yousentech_invoicing_partners
when installed). Automations of other modules on sale-order confirmation are
respected for the delivery; the invoice moment is decided here. Permissions of
other modules (confirming sale orders, creating invoices) apply as they are and
their message is shown to the user.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

AUTO_POST_GROUP = 'yousentech_sale_invoice_automation.post_create_invoice_from_so'
LOCKED_LINE_FIELDS = {
    'service_type_id', 'film_category_id', 'film_category_line_id', 'car_part_id',
    'film_product_id', 'film_product_qty', 'quantity', 'discount_type', 'discount_value',
    'use_manual_price', 'manual_unit_price',
}


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    wof_order_id = fields.Many2one('wof.installation.order', string='أمر التركيب', index=True, copy=False, readonly=True)

    def _get_invoiceable_lines(self, final=False):
        # Stock-only lines (price zero) exist for the delivery, not the invoice.
        lines = super()._get_invoiceable_lines(final=final)
        return lines.filtered(lambda line: not line.wof_stock_only)


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    wof_stock_only = fields.Boolean(string='صرف مخزني فقط', copy=False, readonly=True)
    wof_order_line_id = fields.Many2one('wof.installation.order.line', copy=False, readonly=True, index=True)
    wof_material_line_id = fields.Many2one('wof.installation.material.line', copy=False, readonly=True, index=True)

    @api.depends('wof_stock_only')
    def _compute_qty_to_invoice(self):
        super()._compute_qty_to_invoice()
        for line in self.filtered('wof_stock_only'):
            line.qty_to_invoice = 0.0


class AccountMove(models.Model):
    _inherit = 'account.move'

    wof_order_id = fields.Many2one('wof.installation.order', string='أمر التركيب', index=True, copy=False, readonly=True)

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        for move in posted.filtered(lambda rec: rec.wof_order_id and rec.move_type == 'out_invoice'):
            move.wof_order_id._wof_reconcile_payments(move)
            move.wof_order_id.line_ids._wof_set_commission('invoice', approved=True)
        return posted

    def button_draft(self):
        result = super().button_draft()
        self.filtered('wof_order_id').wof_order_id.line_ids._wof_set_commission('invoice', approved=False)
        return result

    def button_cancel(self):
        result = super().button_cancel()
        self.filtered('wof_order_id').wof_order_id.line_ids._wof_set_commission('invoice', approved=False)
        return result


class WofInstallationOrderLineBilling(models.Model):
    _inherit = 'wof.installation.order.line'

    commission_event = fields.Selection(related='film_category_id.commission_event', string='استحقاق العمولة')
    commission_state = fields.Selection(
        [('pending', 'معلّقة'), ('approved', 'معتمدة')], string='حالة العمولة',
        default='pending', readonly=True, copy=False,
    )
    commission_approved_at = fields.Datetime(string='تاريخ اعتماد العمولة', readonly=True, copy=False)

    def _wof_set_commission(self, event, approved):
        """Approve (or return to pending) the commission of lines whose film uses ``event``."""
        lines = self.filtered(lambda line: (line.commission_event or 'delivery') == event)
        target = 'approved' if approved else 'pending'
        lines = lines.filtered(lambda line: line.commission_state != target)
        if lines:
            lines._write_line_internal({
                'commission_state': target,
                'commission_approved_at': fields.Datetime.now() if approved else False,
            })

    def write(self, vals):
        if LOCKED_LINE_FIELDS.intersection(vals):
            for line in self:
                if line.order_id.sale_order_id.state in ('sale', 'done'):
                    raise ValidationError(_('لا يمكن تعديل الخدمات بعد تأكيد أمر البيع %s.') % line.order_id.sale_order_id.name)
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        orders = self.env['wof.installation.order'].browse([vals.get('order_id') for vals in vals_list if vals.get('order_id')])
        locked = orders.filtered(lambda order: order.sale_order_id.state in ('sale', 'done'))
        if locked:
            raise ValidationError(_('لا يمكن إضافة خدمات بعد تأكيد أمر البيع %s.') % locked[0].sale_order_id.name)
        return super().create(vals_list)


class WofInstallationOrderBilling(models.Model):
    _inherit = 'wof.installation.order'

    picking_ids = fields.Many2many('stock.picking', compute='_compute_wof_pickings', string='الشحنات')
    picking_count = fields.Integer(compute='_compute_wof_pickings')

    @api.depends('sale_order_id.picking_ids')
    def _compute_wof_pickings(self):
        for order in self:
            order.picking_ids = order.sale_order_id.picking_ids
            order.picking_count = len(order.sale_order_id.picking_ids)

    # ------------------------------------------------------------ policy
    def _wof_invoice_moment(self):
        """'manual' | 'confirm' | 'paid' for this order, from the setup."""
        self.ensure_one()
        profile = self.env['wof.company.profile']._wof_get_profile()
        if not profile:
            return 'manual'
        if profile.operation_invoice_by_partner:
            partner = self.partner_id.commercial_partner_id
            credit = 'pay_type' in partner._fields and partner.pay_type == 'credit'
            return 'confirm' if credit else 'paid'
        if profile.payment_policy == 'full_before_invoice':
            return 'paid'
        return 'confirm' if profile.operation_auto_invoice else 'manual'

    def _wof_discount_mode(self):
        profile = self.env['wof.company.profile']._wof_get_profile()
        return profile.invoice_discount_mode if profile else 'visible'

    # ----------------------------------------------------- sale order lines
    def _wof_service_line_values(self, line, mode):
        gross = line.unit_price * line.quantity
        net = gross - line.discount_amount
        if mode == 'net':
            price_unit = net / line.quantity if line.quantity else 0.0
            discount = 0.0
        else:
            price_unit = line.unit_price
            discount = (line.discount_amount / gross * 100.0) if gross else 0.0
        return {
            'product_id': line.service_product_id.id,
            'name': line.service_product_id.display_name or line.car_part_id.name,
            'product_uom_qty': line.quantity,
            'price_unit': price_unit,
            'discount': discount,
            'tax_id': [(6, 0, line.tax_id.ids)],
            'wof_order_line_id': line.id,
        }

    def _wof_note_text(self, line):
        title = line.film_category_id.name or ''
        if line.film_category_line_id:
            title = '%s · %s' % (title, line.film_category_line_id.name)
        description = (line.film_category_id.description or '').strip()
        return '\n'.join(part for part in (title, description) if part)

    def _wof_stock_line_values(self, product, qty, **link):
        values = {
            'product_id': product.id,
            'name': product.display_name,
            'product_uom_qty': qty,
            'price_unit': 0.0,
            'discount': 0.0,
            'tax_id': [(6, 0, [])],
            'wof_stock_only': True,
        }
        values.update(link)
        return values

    def _wof_sale_order_lines(self):
        self.ensure_one()
        mode = self._wof_discount_mode()
        commands = []
        for line in self.line_ids.sorted(lambda rec: (rec.sequence, rec.id)):
            if not line.service_product_id:
                raise ValidationError(_('المكوّن «%s» ليس له صنف خدمي للفوترة.') % line.car_part_id.name)
            commands.append((0, 0, self._wof_service_line_values(line, mode)))
            note = self._wof_note_text(line)
            if note:
                commands.append((0, 0, {'display_type': 'line_note', 'name': note}))
            if line.film_uses_inventory and line.film_product_id and line.film_product_qty > 0:
                commands.append((0, 0, self._wof_stock_line_values(
                    line.film_product_id, line.film_product_qty, wof_order_line_id=line.id)))
        for material in self.material_line_ids.filtered(lambda rec: rec.product_id and rec.quantity > 0):
            commands.append((0, 0, self._wof_stock_line_values(
                material.product_id, material.quantity, wof_material_line_id=material.id)))
        return commands

    # ----------------------------------------------------------- sale order
    def _wof_ensure_sale_order(self):
        """Create and confirm the sale order once; later, add new materials to it."""
        self.ensure_one()
        sale = self.sale_order_id
        if sale and sale.state == 'cancel':
            raise ValidationError(_('أمر البيع المرتبط ملغي. عالجه قبل المتابعة.'))
        if not sale:
            if not self.env['sale.order'].check_access_rights('create', raise_exception=False):
                raise UserError(_('لا تملك صلاحية إنشاء أوامر البيع. اطلب صلاحية «المبيعات» من مسؤول النظام.'))
            values = {
                'partner_id': self.partner_id.id,
                'company_id': self.company_id.id,
                'origin': self.name,
                'client_order_ref': self.vehicle_plate or False,
                'wof_order_id': self.id,
                'order_line': self._wof_sale_order_lines(),
            }
            if self.salesperson_id:
                values['user_id'] = self.salesperson_id.id
            sale = self.env['sale.order'].create(values)
            self._transition_write({'sale_order_id': sale.id})
            self._log_business_event('order.sale_order_created', details={'sale_order': sale.name})
        if sale.state in ('draft', 'sent'):
            # The invoice moment is decided by the car-care setup, not by the
            # sale-order automation, so its automatic invoice is skipped here.
            sale.with_context(skip_invoice_creation=True).action_confirm()
        else:
            self._wof_add_new_materials(sale)
        return sale

    def _wof_add_new_materials(self, sale):
        known = sale.order_line.mapped('wof_material_line_id')
        new = self.material_line_ids.filtered(lambda rec: rec.product_id and rec.quantity > 0 and rec not in known)
        if new:
            sale.write({'order_line': [(0, 0, self._wof_stock_line_values(
                material.product_id, material.quantity, wof_material_line_id=material.id)) for material in new]})

    # -------------------------------------------------------------- invoice
    def _wof_create_invoice(self):
        self.ensure_one()
        if self.invoice_id and self.invoice_id.state != 'cancel':
            return self.invoice_id
        if not self.line_ids:
            raise ValidationError(_('لا توجد خدمات للفوترة.'))
        sale = self._wof_ensure_sale_order()
        invoice = sale._create_invoices()
        if not invoice:
            raise ValidationError(_('لا يوجد ما يُفوتر في أمر البيع %s.') % sale.name)
        invoice = invoice[:1]
        invoice.write({'wof_order_id': self.id})
        self._transition_write({'invoice_id': invoice.id})
        self._log_business_event('order.invoice_created', details={'invoice': invoice.name or invoice.id})
        group = self.env.ref(AUTO_POST_GROUP, raise_if_not_found=False)
        if group and self.env.user in group.users:
            invoice.action_post()
        return invoice

    def action_create_invoice(self):
        self.ensure_one()
        if self.state in ('draft', 'cancelled'):
            raise ValidationError(_('أكّد الأمر قبل إنشاء الفاتورة.'))
        if self._wof_invoice_moment() == 'paid' and not self._wof_is_fully_paid():
            raise ValidationError(_('لا تُنشأ الفاتورة قبل اكتمال الدفع. المتبقي: %s.') % self.amount_residual)
        self._wof_create_invoice()
        return self.action_open_invoice()

    def action_create_sale_order(self):
        self.ensure_one()
        if self.state in ('draft', 'cancelled'):
            raise ValidationError(_('أكّد الأمر قبل إنشاء أمر البيع.'))
        self._wof_ensure_sale_order()
        return self.action_open_sale_order()

    def action_view_pickings(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('stock.action_picking_tree_all')
        action['domain'] = [('id', 'in', self.picking_ids.ids)]
        action['context'] = {'create': False}
        return action

    # ------------------------------------------------------------- triggers
    def action_confirm_arrival(self):
        result = super().action_confirm_arrival()
        for order in self:
            moment = order._wof_invoice_moment()
            if moment == 'confirm' or (moment == 'paid' and order._wof_is_fully_paid()):
                order._wof_create_invoice()
        return result

    def action_deliver(self):
        result = super().action_deliver()
        for order in self:
            # The delivery takes the stock out once the car is handed over.
            order._wof_ensure_sale_order()
            order.line_ids._wof_set_commission('delivery', approved=True)
        return result

    def _wof_after_payment(self):
        result = super()._wof_after_payment()
        for order in self:
            if order._wof_invoice_moment() == 'paid' and order._wof_is_fully_paid() \
                    and order.state not in ('draft', 'cancelled'):
                order._wof_create_invoice()
        return result
