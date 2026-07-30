# -*- coding: utf-8 -*-

from odoo import api, fields, models


class CarParts(models.Model):
    _name = 'wof.car.parts'
    _inherit = ['wof.api.mixin', 'mail.thread']
    _description = 'جزء سيارة'
    _order = 'priority_part, name'
    _check_company_auto = True

    code = fields.Char(
        string="الكود", required=True, index=True, copy=False,
    )
    name = fields.Char(
        string="الاسم", required=True, index=True, translate=True, tracking=True,
    )
    priority_part = fields.Integer(string="ترتيب الأولوية", index=True)
    company_id = fields.Many2one(
        'res.company', string="الشركة", default=lambda self: self.env.company,
        required=True, index=True, ondelete='cascade',
    )
    product_id = fields.Many2one(
        'product.product', string="الصنف الخدمي",
        domain=[('type', '=', 'service')], required=True,
        ondelete='restrict', check_company=True,
    )
    commission = fields.Float(string="عمولة الفني (%)")
    active = fields.Boolean(default=True)
    part_type = fields.Selection(
        [('car_part', 'جزء سيارة'), ('service_area', 'منطقة خدمة')],
        string="نوع الجزء", required=True, default='car_part',
    )
    part_options_required = fields.Boolean(string="الخيارات الإضافية إجبارية")
    film_category_readonly = fields.Boolean(string="فيلم غير قابل للتعديل")
    notes = fields.Char(string="ملاحظات")
    warning_msg = fields.Char(string="رسالة تحذير")
    part_options_ids = fields.Many2many(
        'wof.car.part.options', string="خيارات إضافية",
    )

    _sql_constraints = [
        ('car_part_name_company_unique', 'unique(name, company_id)',
         'جزء السيارة مضاف مسبقًا لنفس الشركة.'),
        ('car_part_code_company_unique', 'unique(code, company_id)',
         'كود جزء السيارة مستخدم مسبقًا لنفس الشركة.'),
        ('car_part_commission_range',
         'check(commission >= 0 AND commission <= 100)',
         'عمولة الفني يجب أن تكون بين 0 و100.'),
    ]

    @api.model
    def name_get(self):
        return [
            (record.id, f'[{record.code}] {record.name}')
            for record in self
        ]

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        domain = list(args or [])
        if name:
            domain = [
                '|', ('name', operator, name), ('code', operator, name),
            ] + domain
        return self.search(domain, limit=limit).name_get()
