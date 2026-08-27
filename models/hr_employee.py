# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    technician_commission_ratio = fields.Float(
        string='نسبة توزيع عمولة الفني (%)',
        default=100.0,
        help='تستخدم عند اختيار توزيع عمولة المكوّن حسب نسبة الفني. '
             'تُعامل كنسبة ترجيح بين الفنيين المشاركين في نفس العمل.',
    )

    @api.constrains('technician_commission_ratio')
    def _check_technician_commission_ratio(self):
        for employee in self:
            if employee.technician_commission_ratio < 0 or employee.technician_commission_ratio > 100:
                raise ValidationError('نسبة توزيع عمولة الفني يجب أن تكون بين 0 و100.')
