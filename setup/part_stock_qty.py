# -*- coding: utf-8 -*-
"""Stock quantity rule of a component: how much film it uses.

A default quantity for the component, and optionally a quantity per car size.
The order uses it only when the film is taken from stock; otherwise the
quantity stays 0.
"""

from odoo import api, fields, models


class CarPartStockQty(models.Model):
    _name = 'wof.car.part.stock.qty'
    _description = 'كمية صرف المكوّن حسب حجم السيارة'
    _order = 'car_size_id'

    part_id = fields.Many2one('wof.car.parts', string='المكوّن', required=True, ondelete='cascade', index=True)
    car_size_id = fields.Many2one('wof.car.size', string='حجم السيارة', required=True, ondelete='cascade')
    qty = fields.Float(string='الكمية', digits='Product Unit of Measure')

    _sql_constraints = [
        ('part_size_unique', 'unique(part_id, car_size_id)', 'لكل حجم سيارة كمية واحدة في المكوّن.'),
        ('qty_positive', 'check(qty >= 0)', 'الكمية لا يمكن أن تكون سالبة.'),
    ]


class CarPartsStockQty(models.Model):
    _inherit = 'wof.car.parts'

    stock_qty = fields.Float(
        string='كمية الصرف الافتراضية', digits='Product Unit of Measure',
        help='تُقترح في أمر التركيب عند صرف الفيلم من المخزون، ما لم يحدد حجم السيارة كمية خاصة.',
    )
    stock_qty_size_ids = fields.One2many('wof.car.part.stock.qty', 'part_id', string='الكمية حسب الحجم')

    def _wof_stock_qty(self, size):
        """Quantity for ``size``: the size's quantity, else the default, else 0."""
        self.ensure_one()
        rule = self.stock_qty_size_ids.filtered(lambda rec: rec.car_size_id == size)[:1] if size else False
        return rule.qty if rule else (self.stock_qty or 0.0)
