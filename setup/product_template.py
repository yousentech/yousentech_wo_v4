# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class xx_categorys_in_product(models.Model):
    _inherit = 'product.template'

    measure_product = fields.Boolean(string="صنف قياس لاوامر التركيب")