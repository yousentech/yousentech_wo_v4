# -*- coding: utf-8 -*-

from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    measure_product = fields.Boolean(string="مادة قياس لأوامر التركيب")
