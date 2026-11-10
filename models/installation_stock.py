# -*- coding: utf-8 -*-
"""Stock product of the film used on an installation-order line.

* The line suggests the tint grade's own stock product, else the film's default
  one, when the film consumes stock ("يصرف مواد من المخزون").
* The product is mandatory when the film says so ("اختيار المنتج المخزني إلزامي").
* When the user is not allowed to sell below zero (yousentech_inventory_minus_quantity,
  read only if installed), a shortage in the user's default warehouse warns while
  editing and blocks the order confirmation, unless the setup allows continuing
  with a warning. The delivery itself never goes negative: that is enforced by the
  stock rules when the delivery is validated.
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools import float_compare

NEGATIVE_GROUP = 'yousentech_inventory_minus_quantity.group_prevent_selling_negative_value'


class WofInstallationOrderStock(models.Model):
    _inherit = 'wof.installation.order'

    def _wof_stock_warehouse(self):
        """The user's default warehouse, else the company's (Odoo standard rule)."""
        return self.env.user.with_company(self.company_id or self.env.company)._get_default_warehouse_id()

    @api.model
    def _wof_negative_blocked(self):
        group = self.env.ref(NEGATIVE_GROUP, raise_if_not_found=False)
        if not group:
            return False
        user = self.env.user
        if 'override_negative_quantities' in user._fields and user.override_negative_quantities \
                and user.negative_quantity_type == 'all_orders':
            return False
        return user in group.users

    def _wof_stock_shortages(self):
        """[(product, needed, available)] for stock products the order lacks."""
        self.ensure_one()
        warehouse = self._wof_stock_warehouse()
        needed = {}
        for line in self.line_ids.filtered(lambda rec: rec.film_product_id and rec.film_uses_inventory):
            needed[line.film_product_id] = needed.get(line.film_product_id, 0.0) + (line.film_product_qty or 0.0)
        shortages = []
        for product, qty in needed.items():
            if product.type != 'product':
                continue
            available = product.with_context(warehouse=warehouse.id).free_qty if warehouse else product.free_qty
            if float_compare(qty, available, precision_rounding=product.uom_id.rounding) > 0:
                shortages.append((product, qty, available))
        return shortages

    def _wof_check_stock_products(self):
        """Called when the order is confirmed."""
        self.ensure_one()
        missing = self.line_ids.filtered(
            lambda rec: rec.film_uses_inventory and rec.film_product_required and not rec.film_product_id
        )
        if missing:
            raise ValidationError(_('حدد الصنف المخزني للخدمات التالية: %s.') % '، '.join(
                missing.mapped(lambda rec: '%s / %s' % (rec.film_category_id.name, rec.car_part_id.name))))
        if not self._wof_negative_blocked():
            return
        shortages = self._wof_stock_shortages()
        if not shortages:
            return
        profile = self.env['wof.company.profile']._wof_get_profile()
        if profile and profile.stock_allow_shortage:
            return
        raise ValidationError(_('الكمية المتاحة لا تكفي في المخزن: %s.') % '، '.join(
            '%s (المطلوب %s، المتاح %s)' % (product.display_name, qty, available)
            for product, qty, available in shortages))

    def _validate_order_basics(self):
        result = super()._validate_order_basics()
        self._wof_check_stock_products()
        return result


class WofInstallationOrderLineStock(models.Model):
    _inherit = 'wof.installation.order.line'

    film_uses_inventory = fields.Boolean(related='film_category_id.is_effected_in_inventory')
    film_product_required = fields.Boolean(related='film_category_id.car_film_product_required')
    film_product_qty = fields.Float(string='كمية الصنف المخزني', default=1.0, digits='Product Unit of Measure')

    @api.model
    def _wof_default_stock_product(self, film, grade):
        if not film or not film.is_effected_in_inventory:
            return self.env['product.product']
        return grade.product_id or film.default_product_id

    @api.onchange('film_category_id', 'film_category_line_id')
    def _onchange_wof_stock_product(self):
        product = self._wof_default_stock_product(self.film_category_id, self.film_category_line_id)
        if product or not self.film_uses_inventory:
            self.film_product_id = product

    @api.onchange('film_product_id', 'film_product_qty')
    def _onchange_wof_stock_shortage(self):
        product = self.film_product_id
        if not product or product.type != 'product' or not self.film_uses_inventory:
            return
        order = self.order_id
        if not order._wof_negative_blocked():
            return
        warehouse = order._wof_stock_warehouse()
        available = product.with_context(warehouse=warehouse.id).free_qty if warehouse else product.free_qty
        if float_compare(self.film_product_qty or 0.0, available, precision_rounding=product.uom_id.rounding) > 0:
            return {'warning': {
                'title': _('الكمية غير كافية'),
                'message': _('المتاح من «%s» في %s هو %s فقط. لن يُصرف بالسالب عند اعتماد الشحنة.') % (
                    product.display_name, warehouse.name if warehouse else _('المخزن'), available),
            }}

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # The grade may be resolved by the base create, so suggest afterwards.
        for line in records.filtered(lambda rec: not rec.film_product_id):
            product = line._wof_default_stock_product(line.film_category_id, line.film_category_line_id)
            if product:
                line.film_product_id = product
        return records
