# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class ServiceType(models.Model):
    _name = 'wof.service.type'
    _inherit = ['wof.api.mixin', 'mail.thread', 'mail.activity.mixin']
    _description = 'نوع خدمة العناية'
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
        string="النوع", default='tint', required=True,
    )
    company_id = fields.Many2one(
        'res.company', string="الشركة", default=lambda self: self.env.company,
        required=True, index=True, ondelete='cascade',
    )
    active = fields.Boolean(string="تفعيل", default=True)
    parts_count = fields.Integer(string="عدد الأجزاء", compute='_compute_counts')
    film_count = fields.Integer(string="عدد الأفلام", compute='_compute_counts')

    _sql_constraints = [
        ('service_name_company_unique', 'unique(name, company_id)',
         'نوع الخدمة مضاف مسبقًا لنفس الشركة.'),
        ('service_code_company_unique', 'unique(code, company_id)',
         'كود الخدمة مستخدم مسبقًا لنفس الشركة.'),
    ]

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
            'name': _('الأفلام'),
            'res_model': 'wof.film.category',
            'view_mode': 'tree,form',
            'domain': [('service_type_id', '=', self.id)],
            'context': {'default_service_type_id': self.id},
        }

    def action_create_film(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('إضافة فيلم'),
            'res_model': 'wof.film.category',
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_service_type_id': self.id},
        }

    def action_open_parts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('الأجزاء المرتبطة'),
            'res_model': 'wof.film.parts.lines',
            'view_mode': 'tree,form',
            'domain': [('service_type_id', '=', self.id)],
        }
