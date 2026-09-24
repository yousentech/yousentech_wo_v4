# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ServiceType(models.Model):
    _name = 'wof.service.type'
    _inherit = ['wof.api.mixin', 'mail.thread', 'mail.activity.mixin']
    _description = 'نشاط مركز العناية'
    _order = 'code, name'
    _check_company_auto = True

    code = fields.Char(
        string="الكود", required=True, index=True, copy=False,
    )
    name = fields.Char(
        string="الاسم", required=True, index=True,
        translate=True, tracking=True,
    )
    service_options = fields.Selection(
        [
            ('tint', 'عزل حراري'),
            ('ppf', 'حماية PPF'),
            ('nano', 'نانو سيراميك'),
            ('upholstery', 'تنجيد'),
            ('floor_mats', 'أرضيات'),
            ('others', 'أخرى'),
        ],
        string="فئة النشاط", default='tint', required=True,
    )
    description = fields.Text(string="وصف النشاط", translate=True)
    supports_color_grades = fields.Boolean(
        string="يدعم درجات لون العزل",
        compute='_compute_supports_color_grades',
    )
    company_id = fields.Many2one(
        'res.company', string="الشركة", default=lambda self: self.env.company,
        required=True, index=True, ondelete='cascade',
    )
    active = fields.Boolean(string="تفعيل", default=True)
    service_ids = fields.One2many(
        'wof.film.category', 'service_type_id', string="خدمات النشاط",
    )
    parts_count = fields.Integer(string="عدد الأجزاء", compute='_compute_counts')
    film_count = fields.Integer(string="عدد الأفلام", compute='_compute_counts')

    _sql_constraints = [
        ('service_name_company_unique', 'unique(name, company_id)',
         'نوع الخدمة مضاف مسبقًا لنفس الشركة.'),
        ('service_code_company_unique', 'unique(code, company_id)',
         'كود الخدمة مستخدم مسبقًا لنفس الشركة.'),
    ]

    @api.depends('service_options')
    def _compute_supports_color_grades(self):
        for record in self:
            record.supports_color_grades = record.service_options == 'tint'

    @api.constrains('service_options')
    def _check_grade_capability_change(self):
        for record in self.filtered(lambda activity: not activity.supports_color_grades):
            graded_services = self.env['wof.film.category'].search_count([
                ('service_type_id', '=', record.id),
                ('film_category_line_ids', '!=', False),
            ])
            if graded_services:
                raise ValidationError(
                    'لا يمكن تغيير فئة النشاط مع وجود درجات لون. '
                    'أرشف الدرجات أو أعد النشاط إلى العزل الحراري.'
                )

    def _compute_counts(self):
        film_groups = self.env['wof.film.category'].read_group(
            [('service_type_id', 'in', self.ids)],
            ['service_type_id'],
            ['service_type_id'],
        )
        film_map = {
            row['service_type_id'][0]: row['service_type_id_count']
            for row in film_groups
            if row.get('service_type_id')
        }
        part_groups = self.env['wof.film.parts.lines'].read_group(
            [('service_type_id', 'in', self.ids)],
            ['service_type_id'],
            ['service_type_id'],
        )
        part_map = {
            row['service_type_id'][0]: row['service_type_id_count']
            for row in part_groups
            if row.get('service_type_id')
        }
        for record in self:
            record.film_count = film_map.get(record.id, 0)
            record.parts_count = part_map.get(record.id, 0)

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

    def action_open_films(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('خدمات النشاط'),
            'res_model': 'wof.film.category',
            'view_mode': 'kanban,tree,form',
            'domain': [('service_type_id', '=', self.id)],
            'context': {'default_service_type_id': self.id},
        }

    def action_create_film(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('إضافة خدمة / فيلم'),
            'res_model': 'wof.film.category',
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_service_type_id': self.id},
        }

    def action_open_services(self):
        return self.action_open_films()

    def action_create_service(self):
        return self.action_create_film()

    def action_open_parts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('الأجزاء المرتبطة'),
            'res_model': 'wof.film.parts.lines',
            'view_mode': 'tree,form',
            'domain': [('service_type_id', '=', self.id)],
        }
