# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FilmPartLineTintPolicy(models.Model):
    _inherit = 'wof.film.parts.lines'

    allowed_grade_ids = fields.Many2many(
        'wof.film.category.lines',
        'wof_film_part_allowed_grade_rel',
        'part_line_id',
        'grade_id',
        string='درجات اللون المسموحة',
        domain="[('header_id', '=', header_id), ('active', '=', True)]",
        check_company=True,
        help='إذا تُرك الحقل فارغًا فلا يطبق قيد إضافي على درجات هذا المكوّن.',
    )
    warning_msg = fields.Char(
        related='car_part_id.warning_msg',
        string='رسالة التحذير',
        readonly=False,
    )

    @api.constrains(
        'header_id', 'car_part_id', 'film_category_line_id', 'allowed_grade_ids'
    )
    def _check_component_tint_policy(self):
        for record in self:
            has_policy = bool(record.film_category_line_id or record.allowed_grade_ids)
            if not has_policy:
                continue
            if record.part_type != 'car_part':
                raise ValidationError(
                    'إعدادات درجات اللون متاحة للمكوّنات فقط ولا تطبق على مناطق الخدمة.'
                )
            if not record.supports_color_grades:
                raise ValidationError(
                    'إعدادات درجات اللون متاحة لمكوّنات العزل الحراري فقط.'
                )
            wrong_grades = record.allowed_grade_ids.filtered(
                lambda grade: grade.header_id != record.header_id
            )
            if wrong_grades:
                raise ValidationError(
                    'درجات اللون المسموحة يجب أن تتبع الخدمة / الفيلم نفسه.'
                )
            if (
                record.film_category_line_id
                and record.allowed_grade_ids
                and record.film_category_line_id not in record.allowed_grade_ids
            ):
                raise ValidationError(
                    'درجة اللون الافتراضية يجب أن تكون ضمن درجات اللون المسموحة.'
                )

    @api.onchange('header_id', 'car_part_id')
    def _onchange_tint_policy_scope(self):
        for record in self:
            if record.part_type != 'car_part' or not record.supports_color_grades:
                record.film_category_line_id = False
                record.allowed_grade_ids = [(5, 0, 0)]

    @api.onchange('allowed_grade_ids')
    def _onchange_allowed_grades_keep_default_valid(self):
        for record in self:
            if (
                record.film_category_line_id
                and record.allowed_grade_ids
                and record.film_category_line_id not in record.allowed_grade_ids
            ):
                record.film_category_line_id = False
