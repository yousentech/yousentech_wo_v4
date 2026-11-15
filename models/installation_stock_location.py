# -*- coding: utf-8 -*-
"""Where the film is taken from: stock location and operation type of the delivery.

Defaults, first match wins:
1. the user's defaults for the branch (user form, tab «مركز العناية»);
2. the branch warehouse: its delivery operation type and that type's source
   location.
The order keeps both, so the availability check, its message and the delivery
use the same place. Changing them is allowed until the sale order exists.
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ResUsersWofStock(models.Model):
    _inherit = 'res.users'

    wof_stock_location_id = fields.Many2one(
        'stock.location', string='موقع المخزن الافتراضي (مركز العناية)', company_dependent=True,
        domain="[('usage', '=', 'internal')]",
        help='يُقترح في أوامر التركيب لهذا المستخدم في الفرع الحالي.')
    wof_picking_type_id = fields.Many2one(
        'stock.picking.type', string='نوع الشحنة الافتراضي (مركز العناية)', company_dependent=True,
        domain="[('code', '=', 'outgoing')]",
        help='نوع عملية التسليم المستخدم لصرف الأفلام في أوامر هذا المستخدم بالفرع الحالي.')

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ['wof_stock_location_id', 'wof_picking_type_id']

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ['wof_stock_location_id', 'wof_picking_type_id']


class WofOrderStockLocation(models.Model):
    _inherit = 'wof.installation.order'

    picking_type_id = fields.Many2one(
        'stock.picking.type', string='نوع الشحنة', check_company=True,
        domain="[('code', '=', 'outgoing'), ('company_id', '=', company_id)]",
        compute='_compute_wof_stock_place', store=True, readonly=False, precompute=True)
    stock_location_id = fields.Many2one(
        'stock.location', string='موقع المخزن', check_company=True,
        domain="[('usage', '=', 'internal'), ('company_id', '=', company_id)]",
        compute='_compute_wof_stock_place', store=True, readonly=False, precompute=True)

    wof_uses_stock = fields.Boolean(string='يصرف من المخزون', compute='_compute_wof_uses_stock')

    @api.depends('line_ids.film_uses_inventory')
    def _compute_wof_uses_stock(self):
        for order in self:
            order.wof_uses_stock = any(order.line_ids.mapped('film_uses_inventory'))

    @api.depends('company_id')
    def _compute_wof_stock_place(self):
        for order in self:
            if order.sale_order_id:
                continue
            company = order.company_id or self.env.company
            user = self.env.user.with_company(company)
            ptype = user.wof_picking_type_id
            if ptype and ptype.company_id != company:
                ptype = self.env['stock.picking.type']
            if not ptype:
                warehouse = user._get_default_warehouse_id()
                ptype = warehouse.out_type_id if warehouse and warehouse.company_id == company else ptype
            location = user.wof_stock_location_id
            if location and location.company_id != company:
                location = self.env['stock.location']
            order.picking_type_id = ptype
            order.stock_location_id = location or ptype.default_location_src_id \
                or (ptype.warehouse_id.lot_stock_id if ptype else False)

    @api.model
    def _wof_can_read_stock(self):
        return all(self.env[model].check_access_rights('read', raise_exception=False)
                   for model in ('stock.quant', 'stock.move'))

    def _wof_free_qty(self, product, location=None):
        """Free quantity of ``product`` where the order takes its stock, or None when
        the user cannot read stock (technicians) or the product is not stocked."""
        if not product or product.type != 'product' or not self._wof_can_read_stock():
            return None
        location = location if location is not None else (self._wof_stock_location() if self else False)
        return (product.with_context(location=location.id) if location else product).free_qty

    def _wof_product_choices(self, products):
        """Products for a picker with what is free in the order's location."""
        self.ensure_one()
        location = self._wof_stock_location()
        result = []
        for product in products:
            free = self._wof_free_qty(product, location)
            result.append({'id': product.id, 'name': product.display_name, 'stocked': free is not None,
                           'available': round(free or 0.0, 3), 'uom': product.uom_id.name or ''})
        return result

    def _wof_stock_location(self):
        self.ensure_one()
        return self.stock_location_id or self.picking_type_id.default_location_src_id \
            or self._wof_stock_warehouse().lot_stock_id

    def write(self, vals):
        if {'picking_type_id', 'stock_location_id'} & set(vals):
            for order in self:
                if order.sale_order_id and order.sale_order_id.picking_ids.filtered(lambda p: p.state == 'done'):
                    raise ValidationError(_('لا يمكن تغيير موقع المخزن بعد اعتماد الشحنة.'))
        return super().write(vals)

    def _wof_apply_stock_place(self, sale):
        """Send the delivery from the order's place."""
        location = self._wof_stock_location()
        ptype = self.picking_type_id
        for picking in sale.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel')
                                                 and p.picking_type_code == 'outgoing'):
            vals = {}
            if ptype and picking.picking_type_id != ptype:
                vals['picking_type_id'] = ptype.id
            if location and picking.location_id != location:
                vals['location_id'] = location.id
            if not vals:
                continue
            moving = 'location_id' in vals
            if moving:
                # Reservations were made in the old place: release them first.
                picking.do_unreserve()
            picking.write(vals)
            if moving:
                picking.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')).write(
                    {'location_id': location.id})
                picking.action_assign()

    def _wof_sale_warehouse(self):
        location = self._wof_stock_location()
        return location.warehouse_id or self.picking_type_id.warehouse_id

    def _wof_stock_diagnosis(self, sale=None):
        """Lines explaining the stock of the order's products where the check looks."""
        self.ensure_one()
        location = self._wof_stock_location()
        warehouse = (sale.warehouse_id if sale else False) or self._wof_sale_warehouse()
        products = self.env['product.product']
        for line in self.line_ids:
            for product, _qty in line._wof_stock_needs():
                products |= product
        products |= self.material_line_ids.product_id
        lines = []
        if not self._wof_can_read_stock():
            return [_('• لا تملك صلاحية الاطلاع على المخزون لعرض التفاصيل.')]
        for product in products.filtered(lambda rec: rec.type == 'product'):
            in_wh = product.with_context(warehouse=warehouse.id) if warehouse else product
            in_loc = product.with_context(location=location.id) if location else product
            moves = self.env['stock.move.line'].search([
                ('product_id', '=', product.id), ('state', 'not in', ('done', 'cancel')),
                ('location_id', 'child_of', (warehouse.view_location_id.id if warehouse else location.id)),
            ], limit=5)
            holders = ', '.join(sorted(set(moves.mapped(lambda rec: rec.picking_id.name or rec.reference or ''))))
            lines.append(_('• %(p)s: في المستودع «%(w)s» موجود %(on)s، محجوز %(res)s، الحر %(free)s؛ '
                           'في الموقع «%(l)s» الحر %(lfree)s%(by)s') % {
                'p': product.display_name, 'w': warehouse.name if warehouse else '-',
                'on': in_wh.qty_available, 'res': in_wh.qty_available - in_wh.free_qty, 'free': in_wh.free_qty,
                'l': location.complete_name if location else '-', 'lfree': in_loc.free_qty,
                'by': (_(' — محجوز في: %s') % holders) if holders else '',
            })
        return lines

    def _wof_ensure_sale_order(self):
        warehouse = self._wof_sale_warehouse()
        try:
            with self.env.cr.savepoint():
                if not self.sale_order_id and warehouse:
                    sale = super(WofOrderStockLocation, self.with_context(
                        wof_sale_warehouse_id=warehouse.id,
                        wof_sale_picking_type_id=self.picking_type_id.id))._wof_ensure_sale_order()
                else:
                    sale = super()._wof_ensure_sale_order()
                self._wof_apply_stock_place(sale)
        except ValidationError as error:
            message = str(error.args[0] if error.args else error)
            if 'available quantity' not in message and 'الكمية المتاحة' not in message:
                raise
            details = self._wof_stock_diagnosis()
            raise ValidationError('%s\n\n%s\n%s\n\n%s' % (
                message, _('تفاصيل المخزون حيث يتم الفحص:'), '\n'.join(details),
                _('الفحص يطرح الكميات المحجوزة لشحنات أخرى لم تُسلَّم بعد. سلّم أو ألغِ تلك الشحنات، '
                  'أو غيّر موقع المخزن في كارد «الفرع والفريق».'))) from error
        return sale


class SaleOrderWofWarehouse(models.Model):
    _inherit = 'sale.order'

    @api.model_create_multi
    def create(self, vals_list):
        warehouse = self.env.context.get('wof_sale_warehouse_id')
        ptype = self.env.context.get('wof_sale_picking_type_id')
        if warehouse:
            for vals in vals_list:
                vals.setdefault('warehouse_id', warehouse)
                # Some installed modules add a delivery type on the sale order.
                if ptype and 'picking_type_id' in self._fields:
                    vals.setdefault('picking_type_id', ptype)
        return super().create(vals_list)


class WofOrderStockSummary(models.Model):
    _inherit = 'wof.installation.order'

    stock_summary_html = fields.Html(string='أصناف المخزون من الخدمات', compute='_compute_stock_summary_html',
                                     sanitize=False)

    @api.depends('line_ids.film_product_id', 'line_ids.film_product_qty', 'line_ids.part_line_ids.product_id',
                 'line_ids.part_line_ids.product_qty', 'stock_location_id', 'material_line_ids.quantity')
    def _compute_stock_summary_html(self):
        from markupsafe import Markup, escape
        for order in self:
            rows = []
            totals = {}
            for line in order.line_ids.filtered('film_uses_inventory'):
                for product, qty in line._wof_stock_needs():
                    totals[product] = totals.get(product, 0.0) + qty
            for material in order.material_line_ids.filtered('product_id'):
                totals[material.product_id] = totals.get(material.product_id, 0.0) + (material.quantity or 0.0)
            for line in order.line_ids.filtered('film_uses_inventory'):
                if line.part_line_ids:
                    items = [('%s / %s' % (line.car_part_id.name, part.part_id.name), part.product_id, part.product_qty)
                             for part in line.part_line_ids]
                else:
                    items = [(line.car_part_id.name, line.film_product_id, line.film_product_qty)]
                location = order._wof_stock_location()
                for label, product, qty in items:
                    free = order._wof_free_qty(product, location)
                    # Lines sharing a product draw on the same stock: compare the total.
                    short = free is not None and qty and totals.get(product, qty) > free
                    rows.append(Markup('<tr class="%s"><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>') % (
                        'is-short' if short else ('is-zero' if not qty else ''),
                        escape(label or ''),
                        escape(product.display_name) if product else Markup('<span class="wof_ex_warn">غير محدد</span>'),
                        Markup('<span class="wof_ex_warn">0 — حدّد الكمية</span>') if not qty else qty,
                        '—' if free is None else Markup('<span class="%s">%s</span>') % (
                            'wof_ex_bad' if short else 'wof_ex_ok', round(free, 3))))
            if not rows:
                order.stock_summary_html = Markup('<p class="text-muted">لا تصرف خدمات هذا الأمر من المخزون.</p>')
                continue
            location = order._wof_stock_location()
            order.stock_summary_html = Markup(
                '<table class="table table-sm wof_stock_sum"><thead><tr><th>الخدمة / الجزء</th><th>الصنف</th>'
                '<th>الكمية</th><th>المتاح في الموقع</th></tr></thead><tbody>%s</tbody></table>'
                '<small class="text-muted">تُصرف من «%s» عبر شحنة أمر البيع عند التسليم. عدّل الصنف والكمية من كارد الخدمة.</small>'
            ) % (Markup('').join(rows), escape(location.complete_name if location else 'المخزن'))
