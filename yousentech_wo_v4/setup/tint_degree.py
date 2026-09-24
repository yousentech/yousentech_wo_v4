# -*- coding: utf-8 -*-

from odoo import fields, models


class WofTintDegree(models.Model):
    _name = 'wof.tint.degree'
    _inherit = ['wof.api.mixin']
    _description = 'درجات اللون الرسمية للمركز'
    _order = 'sequence, id'
    _check_company_auto = True

    sequence = fields.Integer(default=10)
    value = fields.Char(string='درجة اللون', required=True, index=True)
    # Kept nullable for safe upgrades from older databases that already had
    # wof.tint.degree rows; setup activation fills it for managed degrees.
    code = fields.Char(string='الكود', index=True, copy=False)
    numbering_method = fields.Selection(
        [('sequential', 'ترقيم تسلسلي'), ('percentage', 'ترقيم بالنسب')],
        string='طريقة الترقيم', index=True,
    )
    company_id = fields.Many2one(
        'res.company', string='الشركة', required=True,
        default=lambda self: self.env.company, ondelete='cascade', index=True,
    )
    is_setup_default = fields.Boolean(default=True, readonly=True, copy=False)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('tint_degree_value_company_unique', 'unique(value, company_id)',
         'درجة اللون موجودة مسبقًا لهذه الشركة.'),
        ('tint_degree_code_company_unique', 'unique(code, company_id)',
         'كود درجة اللون موجود مسبقًا لهذه الشركة.'),
    ]
