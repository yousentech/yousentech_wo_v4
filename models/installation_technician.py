# -*- coding: utf-8 -*-
"""Technicians of an installation order.

Technicians are HR employees flagged «فني تركيب». The order keeps one
assignment record per technician; the assignment stores the technician's name
and user, so an order keeps showing (and reporting) its technicians after one of
them moves to another branch, even for users who cannot see that branch.
The branch rule (same company as the order) applies only when choosing a
technician, never to records already saved.
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

TEAM_STATES = ('draft', 'scheduled', 'intake', 'in_progress')


class WofHrEmployeeTechnician(models.Model):
    _inherit = 'hr.employee'

    is_wof_technician = fields.Boolean(
        string='فني تركيب', tracking=True,
        help='يظهر الموظف في قائمة فنيي أوامر التركيب لفرعه (شركته).',
    )


class WofInstallationOrderTechnician(models.Model):
    _name = 'wof.installation.order.technician'
    _description = 'فني أمر التركيب'
    _order = 'sequence, id'
    _rec_name = 'name'

    sequence = fields.Integer(default=10)
    order_id = fields.Many2one(
        'wof.installation.order', string='أمر التركيب', required=True,
        ondelete='cascade', index=True,
    )
    company_id = fields.Many2one(
        related='order_id.company_id', store=True, readonly=True, index=True,
    )
    employee_id = fields.Many2one(
        'hr.employee', string='الفني', required=True, ondelete='restrict', index=True,
    )
    # Stored so the name and user stay readable whatever branch the employee is in now.
    name = fields.Char(related='employee_id.name', store=True, readonly=True, string='اسم الفني')
    user_id = fields.Many2one(
        related='employee_id.user_id', store=True, readonly=True, index=True, string='مستخدم الفني',
    )
    job_title = fields.Char(related='employee_id.job_title', readonly=True, string='المسمى')
    service_count = fields.Integer(string='الخدمات المسندة', compute='_compute_service_count')

    _sql_constraints = [
        ('order_employee_unique', 'unique(order_id, employee_id)', 'هذا الفني مضاف مسبقًا لأمر التركيب.'),
    ]

    def _compute_service_count(self):
        for rec in self:
            rec.service_count = len(rec.order_id.line_ids.filtered(lambda line: line.execution_technician_id == rec))

    @api.constrains('employee_id', 'order_id')
    def _check_technician_branch(self):
        # Checked only when a technician is chosen: a later move to another
        # branch never invalidates orders already saved.
        if self.env.context.get('wof_skip_technician_check'):
            return
        Employee = self.env['hr.employee']
        for rec in self:
            # A search (not a read) so an employee of a branch the user cannot see
            # gives the clear message below instead of an access error.
            allowed = Employee.search_count([
                ('id', '=', rec.employee_id.id), ('is_wof_technician', '=', True),
                ('company_id', 'in', [rec.order_id.company_id.id, False]),
            ])
            if not allowed:
                raise ValidationError(
                    _('«%s» ليس فني تركيب في فرع هذا الأمر. اختر من فنيي الفرع المعلَّمين «فني تركيب».') % rec.name)

    def _check_team_editable(self):
        for order in self.order_id:
            order._wof_check_team_editable()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get('wof_skip_technician_check'):
            records._check_team_editable()
        return records

    def write(self, vals):
        if set(vals) - {'sequence'}:
            self._check_team_editable()
        return super().write(vals)

    def unlink(self):
        self._check_team_editable()
        used = self.env['wof.installation.order.line'].search([('execution_technician_id', 'in', self.ids)])
        if used:
            raise ValidationError(
                _('لا يمكن إزالة فني مسند إلى خدمة. أعد إسناد الخدمات أولًا: %s.')
                % '، '.join(used.execution_technician_id.mapped('name'))
            )
        return super().unlink()


class WofInstallationOrderTeam(models.Model):
    _inherit = 'wof.installation.order'

    technician_ids = fields.One2many(
        'wof.installation.order.technician', 'order_id', string='الفنيون', copy=False,
    )
    technician_names = fields.Char(
        string='أسماء الفنيين', compute='_compute_technician_names', store=True,
    )
    amount_gross = fields.Monetary(string='قيمة الخدمات', compute='_compute_order_summary')
    service_count = fields.Integer(string='عدد الخدمات', compute='_compute_order_summary')
    technician_count = fields.Integer(string='عدد الفنيين', compute='_compute_order_summary')
    wof_paid_percent = fields.Float(string='نسبة المدفوع', compute='_compute_order_summary')

    @api.depends('amount_untaxed', 'amount_discount', 'line_ids', 'technician_ids', 'amount_total', 'amount_paid')
    def _compute_order_summary(self):
        for order in self:
            order.amount_gross = order.amount_untaxed + order.amount_discount
            order.service_count = len(order.line_ids)
            order.technician_count = len(order.technician_ids)
            order.wof_paid_percent = min(100.0, order.amount_paid * 100.0 / order.amount_total) \
                if order.amount_total > 0 else 0.0

    # ---------------------------------------------------------------- branch
    @api.onchange('company_id')
    def _onchange_wof_branch(self):
        # Technicians of the previous branch leave the order with it.
        keep = self.technician_ids.filtered(
            lambda rec: not rec.employee_id.company_id or rec.employee_id.company_id == self.company_id)
        if keep != self.technician_ids:
            self.technician_ids = keep
            return {'warning': {
                'title': _('تغيير الفرع'),
                'message': _('أُزيل فنيو الفرع السابق من الأمر. اختر فنيي الفرع الجديد.'),
            }}

    def write(self, vals):
        if 'company_id' not in vals:
            return super().write(vals)
        company = self.env['res.company'].browse(vals['company_id']).exists()
        changing = self.filtered(lambda order: order.company_id != company)
        if changing:
            if not company or company not in self.env.companies:
                raise ValidationError(_('اختر فرعًا من الفروع المسموح لك بالعمل عليها.'))
            for order in changing:
                if order.state not in ('draft', 'scheduled'):
                    raise ValidationError(_('يُغيَّر فرع الأمر قبل إكمال الاستلام فقط.'))
                paid = self.env['account.payment'].search_count([('wof_order_id', '=', order.id)]) \
                    if self.env['account.payment'].check_access_rights('read', raise_exception=False) else 0
                if paid or order.sale_order_id or order.invoice_id:
                    raise ValidationError(_('لا يمكن تغيير الفرع بعد تسجيل دفعات أو إنشاء أمر بيع أو فاتورة.'))
        result = super().write(vals)
        Employee = self.env['hr.employee']
        for order in changing:
            outside = order.technician_ids.filtered(lambda rec: not Employee.search_count([
                ('id', '=', rec.employee_id.id), ('company_id', 'in', [company.id, False])]))
            if outside:
                raise ValidationError(_('الفنيون التاليون من فرع آخر، أزلهم أولًا: %s.') % '، '.join(outside.mapped('name')))
        return result

    @api.depends('technician_ids.name')
    def _compute_technician_names(self):
        for order in self:
            order.technician_names = '، '.join(name for name in order.technician_ids.mapped('name') if name) or False

    def _wof_is_assigned_technician(self, user=None):
        self.ensure_one()
        return (user or self.env.user) in self.technician_ids.user_id

    def _wof_check_team_editable(self):
        for order in self:
            order._ensure_role(
                'yousentech_wo_v4.group_wo_user',
                'yousentech_wo_v4.group_wo_supervisor',
                'yousentech_wo_v4.group_wo_manager',
            )
            if order.state not in TEAM_STATES:
                raise ValidationError(_('لا يمكن تغيير فريق العمل بعد إرسال الأمر إلى فحص الجودة.'))
