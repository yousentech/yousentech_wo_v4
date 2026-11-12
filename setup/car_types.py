# -*- coding: utf-8 -*-

import re

from odoo import api, fields, models


def _auto_code(name, model, extra=None):
    """Code for a record created from a dropdown: from the name, unique."""
    base = re.sub(r'[^A-Z0-9]', '', (name or '').upper())[:16] or 'CAR'
    code, n = base, 1
    while model.with_context(active_test=False).search_count([('code', '=', code)] + (extra or [])):
        n += 1
        code = '%s%s' % (base, n)
    return code


class CarManufactory(models.Model):
    _name = 'wof.car.manufactory'
    _inherit = ['wof.api.mixin']
    _description = 'الشركة المصنعة للسيارة'
    _order = 'name'

    code = fields.Char(string="الكود", index=True, copy=False, help="يُولَّد تلقائيًا من الاسم إذا تُرك فارغًا.")
    name = fields.Char(
        string="الاسم", required=True, index=True, translate=True,
    )
    active = fields.Boolean(string="تفعيل", default=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('code'):
                vals['code'] = _auto_code(vals.get('name'), self)
        return super().create(vals_list)

    _sql_constraints = [
        ('car_manufactory_code_unique', 'unique(code)',
         'كود الشركة المصنعة مستخدم مسبقًا.'),
        ('car_manufactory_name_unique', 'unique(name)',
         'الشركة المصنعة مضافة مسبقًا.'),
    ]


class CarType(models.Model):
    _name = 'wof.car.type'
    _inherit = ['wof.api.mixin']
    _description = 'طراز السيارة'
    _order = 'manufactory_id, name'

    code = fields.Char(string="الكود", index=True, copy=False, help="يُولَّد تلقائيًا من الاسم إذا تُرك فارغًا.")
    name = fields.Char(
        string="الاسم", required=True, index=True, translate=True,
    )
    manufactory_id = fields.Many2one(
        'wof.car.manufactory', string="الشركة المصنعة",
        required=True, ondelete='restrict', index=True,
    )
    active = fields.Boolean(string="تفعيل", default=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('code'):
                vals['code'] = _auto_code(vals.get('name'), self, [('manufactory_id', '=', vals.get('manufactory_id'))])
        return super().create(vals_list)

    _sql_constraints = [
        ('car_type_code_manufactory_unique',
         'unique(code, manufactory_id)',
         'كود طراز السيارة مستخدم مسبقًا لدى الشركة المصنعة.'),
        ('car_type_name_manufactory_unique',
         'unique(name, manufactory_id)',
         'طراز السيارة مضاف مسبقًا لدى الشركة المصنعة.'),
    ]
