# -*- coding: utf-8 -*-
"""Accessories and extra sales on an installation order (ملحقات ومبيعات إضافية).

Anything sold with the order besides its services: a service product or a
stock product, at a selling price. Extras are part of the order total and go to
the sale order as priced lines, so they are invoiced with the services; stock
products leave through the same delivery. They can be changed until the sale
order is confirmed, like the services.
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class WofInstallationExtraLine(models.Model):
    _name = 'wof.installation.extra.line'
    _description = 'ملحق أو بيع إضافي في أمر التركيب'
    _order = 'sequence, id'
    _check_company_auto = True

    order_id = fields.Many2one('wof.installation.order', string='أمر التركيب', required=True,
                               ondelete='cascade', index=True, check_company=True)
    company_id = fields.Many2one(related='order_id.company_id', store=True, readonly=True)
    currency_id = fields.Many2one(related='order_id.currency_id', store=True, readonly=True)
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one(
        'product.product', string='الصنف', required=True, check_company=True,
        domain="[('sale_ok', '=', True), ('type', 'in', ('service', 'product', 'consu')), "
               "('company_id', 'in', [company_id, False])]")
    product_type = fields.Selection(related='product_id.type', string='نوع الصنف')
    name = fields.Char(string='الوصف')
    quantity = fields.Float(string='الكمية', default=1.0, required=True, digits='Product Unit of Measure')
    uom_id = fields.Many2one(related='product_id.uom_id', string='الوحدة')
    price_unit = fields.Float(string='سعر البيع', digits='Product Price')
    tax_ids = fields.Many2many('account.tax', string='الضريبة', check_company=True,
                               domain="[('type_tax_use', '=', 'sale'), ('company_id', '=', company_id)]")
    amount_untaxed = fields.Monetary(string='قبل الضريبة', compute='_compute_amounts', store=True)
    amount_tax = fields.Monetary(string='الضريبة', compute='_compute_amounts', store=True)
    amount_total = fields.Monetary(string='الإجمالي', compute='_compute_amounts', store=True)
    available_qty = fields.Float(string='المتاح في الموقع', compute='_compute_available', digits='Product Unit of Measure')
    is_short = fields.Boolean(compute='_compute_available')

    _sql_constraints = [
        ('quantity_positive', 'check(quantity > 0)', 'كمية الملحق يجب أن تكون أكبر من صفر.'),
        ('price_not_negative', 'check(price_unit >= 0)', 'سعر الملحق لا يمكن أن يكون سالبًا.'),
    ]

    @api.depends('quantity', 'price_unit', 'tax_ids', 'product_id')
    def _compute_amounts(self):
        for line in self:
            base = line.price_unit * line.quantity
            if line.tax_ids:
                taxes = line.tax_ids.compute_all(line.price_unit, currency=line.currency_id, quantity=line.quantity,
                                                 product=line.product_id, partner=line.order_id.partner_id)
                line.amount_untaxed = taxes['total_excluded']
                line.amount_total = taxes['total_included']
            else:
                line.amount_untaxed = line.amount_total = base
            line.amount_tax = line.amount_total - line.amount_untaxed

    @api.depends('product_id', 'quantity', 'order_id.stock_location_id')
    def _compute_available(self):
        for line in self:
            product = line.product_id
            if not product or product.type != 'product' or not line.order_id:
                line.available_qty = 0.0
                line.is_short = False
                continue
            free = line.order_id._wof_free_qty(product)
            line.available_qty = free or 0.0
            line.is_short = free is not None and line.quantity > free

    @api.model
    def _wof_default_taxes(self, order, product):
        profile = self.env['wof.company.profile']._wof_get_profile()
        if profile and profile.operation_tax_enabled and profile.operation_tax_id:
            return profile.operation_tax_id
        if profile and not profile.operation_tax_enabled:
            return self.env['account.tax']
        return product.taxes_id.filtered(lambda tax: tax.company_id == order.company_id)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        product = self.product_id
        if not product:
            return
        order = self.order_id
        self.name = product.get_product_multiline_description_sale() or product.display_name
        pricelist = order.partner_id.property_product_pricelist if order.partner_id else False
        self.price_unit = pricelist._get_product_price(product, self.quantity or 1.0) if pricelist else product.lst_price
        self.tax_ids = self._wof_default_taxes(order, product)

    # ------------------------------------------------------------ rules
    def _wof_check_editable(self, orders):
        for order in orders:
            order._ensure_role(
                'yousentech_wo_v4.group_wo_user', 'yousentech_wo_v4.group_wo_supervisor',
                'yousentech_wo_v4.group_wo_manager')
            if order.state in ('delivered', 'cancelled'):
                raise ValidationError(_('لا يمكن تعديل الملحقات بعد تسليم الأمر أو إلغائه.'))
            if order.sale_order_id.state in ('sale', 'done'):
                raise ValidationError(_('لا يمكن تعديل الملحقات بعد تأكيد أمر البيع %s.') % order.sale_order_id.name)

    @api.model_create_multi
    def create(self, vals_list):
        orders = self.env['wof.installation.order'].browse({vals['order_id'] for vals in vals_list if vals.get('order_id')})
        self._wof_check_editable(orders)
        lines = super().create(vals_list)
        for line in lines:
            # Defaults when created without the form (price, description, tax).
            values = {}
            if not line.name:
                values['name'] = line.product_id.get_product_multiline_description_sale() or line.product_id.display_name
            if 'tax_ids' not in next((v for v in vals_list if v.get('product_id') == line.product_id.id), {}):
                values['tax_ids'] = [(6, 0, self._wof_default_taxes(line.order_id, line.product_id).ids)]
            if values:
                super(WofInstallationExtraLine, line).write(values)
        return lines

    def write(self, vals):
        self._wof_check_editable(self.order_id)
        return super().write(vals)

    def unlink(self):
        self._wof_check_editable(self.order_id)
        return super().unlink()


class WofInstallationOrderExtras(models.Model):
    _inherit = 'wof.installation.order'

    extra_line_ids = fields.One2many('wof.installation.extra.line', 'order_id', string='الملحقات والمبيعات الإضافية',
                                     copy=False)
    amount_extras = fields.Monetary(string='الملحقات', compute='_compute_amounts', store=True)

    @api.depends('line_ids.amount_untaxed', 'line_ids.discount_amount', 'line_ids.amount_tax',
                 'line_ids.amount_total', 'extra_line_ids.amount_untaxed', 'extra_line_ids.amount_tax',
                 'extra_line_ids.amount_total')
    def _compute_amounts(self):
        super()._compute_amounts()
        for order in self:
            extras = order.extra_line_ids
            order.amount_extras = sum(extras.mapped('amount_untaxed'))
            order.amount_untaxed += order.amount_extras
            order.amount_tax += sum(extras.mapped('amount_tax'))
            order.amount_total += sum(extras.mapped('amount_total'))

    def _wof_extra_sale_lines(self):
        self.ensure_one()
        return [(0, 0, {
            'product_id': extra.product_id.id,
            'name': extra.name or extra.product_id.display_name,
            'product_uom_qty': extra.quantity,
            'price_unit': extra.price_unit,
            'discount': 0.0,
            'tax_id': [(6, 0, extra.tax_ids.ids)],
            'wof_extra_line_id': extra.id,
        }) for extra in self.extra_line_ids]

    def _wof_sale_order_lines(self):
        commands = super()._wof_sale_order_lines()
        if self.extra_line_ids:
            commands.append((0, 0, {'display_type': 'line_section', 'name': _('ملحقات ومبيعات إضافية')}))
            commands += self._wof_extra_sale_lines()
        return commands


class SaleOrderLineExtra(models.Model):
    _inherit = 'sale.order.line'

    wof_extra_line_id = fields.Many2one('wof.installation.extra.line', copy=False, readonly=True, index=True)

    @api.depends('wof_extra_line_id')
    def _compute_qty_to_invoice(self):
        super()._compute_qty_to_invoice()
        # Sold with the order: invoiced with the services, before the delivery.
        for line in self.filtered(lambda rec: rec.wof_extra_line_id and rec.order_id.state in ('sale', 'done')):
            line.qty_to_invoice = line.product_uom_qty - line.qty_invoiced
