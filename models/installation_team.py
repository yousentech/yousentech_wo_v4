# -*- coding: utf-8 -*-
"""Installation team: which employees work as technicians or operations
supervisors, in which branch, and the technician's commission share.

One row per employee and branch. Moving a technician to another branch means
editing (or adding) his row: orders already saved keep their technicians and
names, nothing checks them again.
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class WofTeamMember(models.Model):
    _name = 'wof.team.member'
    _description = 'عضو فريق التركيب'
    _order = 'company_id, name'
    _rec_name = 'name'

    employee_id = fields.Many2one('hr.employee', string='الموظف', required=True, ondelete='cascade', index=True)
    name = fields.Char(related='employee_id.name', store=True, readonly=True, string='الاسم')
    user_id = fields.Many2one(related='employee_id.user_id', store=True, readonly=True, string='المستخدم')
    job_title = fields.Char(related='employee_id.job_title', readonly=True, string='المسمى')
    company_id = fields.Many2one(
        'res.company', string='الفرع', required=True, index=True, default=lambda self: self.env.company,
        help='الفرع الذي يعمل فيه في أوامر التركيب.')
    is_technician = fields.Boolean(string='فني', default=True)
    is_supervisor = fields.Boolean(string='مشرف تشغيل')
    commission_ratio = fields.Float(
        string='نسبة عمولة الفني (%)', default=100.0,
        help='تُستخدم عند توزيع عمولة المكوّن حسب نسبة الفني، كنسبة ترجيح بين الفنيين المشاركين.')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('employee_branch_unique', 'unique(employee_id, company_id)', 'الموظف مضاف مسبقًا لفريق هذا الفرع.'),
    ]

    @api.constrains('is_technician', 'is_supervisor')
    def _check_role(self):
        for member in self:
            if not member.is_technician and not member.is_supervisor:
                raise ValidationError(_('حدد دور «%s»: فني أو مشرف تشغيل.') % member.name)

    @api.constrains('commission_ratio')
    def _check_ratio(self):
        for member in self:
            if not 0 <= member.commission_ratio <= 100:
                raise ValidationError(_('نسبة عمولة الفني يجب أن تكون بين 0 و100.'))

    @api.model
    def _wof_employees(self, company, role):
        """Active team employees of a branch for a role ('technician' or 'supervisor')."""
        if not company:
            return self.env['hr.employee']
        field = 'is_technician' if role == 'technician' else 'is_supervisor'
        return self.search([('company_id', '=', company.id), (field, '=', True)]).employee_id
