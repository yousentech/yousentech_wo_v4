# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class TintDegree(models.Model):
    _name = 'wof.tint.degree'
    _description = 'Tint Degree'
    _rec_name = 'display_name'
    _order = 'sequence, value'

    sequence = fields.Integer(
        string="الترتيب",
        default=10,
        index=True
    )

    name = fields.Char(
        string="المسمى",
        required=True,
        index=True,
        translate=True
    )

    value = fields.Char(
        string="القيمة",
        required=True,
        index=True
    )

    active = fields.Boolean(
        string="تفعيل",
        default=True
    )

    is_default_setup = fields.Boolean(
        string="بيانات افتراضية",
        default=False,
        copy=False,
        index=True,
        help="تم إنشاؤها من التهيئة الافتراضية ويمكن إعادة تحميلها بأمان."
    )

    def _default_company_parent(self):
        company = self.env.company
        return company.parent_id or company

    company_id = fields.Many2one(
        'res.company',
        string="الشركة",
        default=_default_company_parent,
        required=True,
        index=True
    )

    display_name = fields.Char(
        string="الاسم المعروض",
        compute="_compute_display_name",
        store=True
    )

    @api.depends('name', 'value')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "%s - %s" % (rec.name or '', rec.value or '')

    _sql_constraints = [
        (
            "tint_degree_value_company_unique",
            "UNIQUE(value, company_id)",
            "قيمة درجة اللون مضافة مسبقاً لنفس الشركة"
        ),
    ]


class FilmCategoryLineInherit(models.Model):
    _inherit = 'wof.film.category.lines'

    sequence = fields.Integer(
        string="الترتيب",
        default=10
    )

    tint_degree_id = fields.Many2one(
        'wof.tint.degree',
        string="درجة اللون الأساسية",
        ondelete='restrict'
    )

    degree_label = fields.Char(
        string="مسمى الدرجة"
    )

    degree_value = fields.Char(
        string="قيمة الدرجة"
    )