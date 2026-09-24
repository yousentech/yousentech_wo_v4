# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


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
    service_area_part_ids = fields.Many2many(
        'wof.car.parts',
        'wof_car_parts_service_area_rel',
        'service_area_id', 'child_part_id',
        string="أجزاء منطقة الخدمة",
        domain="[('company_id', '=', company_id), ('part_type', '=', 'car_part'), ('active', '=', True)]",
        help="تُستخدم فقط عندما يكون نوع المكوّن منطقة خدمة. هذه الأجزاء بنيوية/تشغيلية، بينما تسعير المنطقة وعمولتها يتمان كوحدة تجارية واحدة.",
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

    @api.constrains('part_type', 'service_area_part_ids', 'company_id')
    def _check_service_area_parts(self):
        for record in self:
            if record.part_type != 'service_area' and record.service_area_part_ids:
                raise ValidationError('يمكن تحديد أجزاء داخلية فقط للمكوّن من نوع منطقة خدمة.')
            if record in record.service_area_part_ids:
                raise ValidationError('لا يمكن أن تحتوي منطقة الخدمة على نفسها.')
            wrong_type = record.service_area_part_ids.filtered(lambda part: part.part_type != 'car_part')
            if wrong_type:
                raise ValidationError('منطقة الخدمة يمكن أن تحتوي فقط على مكونات معرفة كأجزاء سيارة.')
            wrong_company = record.service_area_part_ids.filtered(lambda part: part.company_id != record.company_id)
            if wrong_company:
                raise ValidationError('جميع أجزاء منطقة الخدمة يجب أن تتبع نفس الشركة.')

    @api.onchange('part_type')
    def _onchange_part_type_clear_service_area_parts(self):
        if self.part_type != 'service_area':
            self.service_area_part_ids = [(5, 0, 0)]

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
