# -*- coding: utf-8 -*-
"""People of an installation order.

* Technicians are HR employees flagged «فني تركيب» and are chosen per service
  (one or more on each component).
* The service advisor and the operations supervisor are HR employees.
* The salesman comes from the salesmen module, among those assigned to the
  order's branch.

Branch (company) checks run only when a person is chosen. A technician or
employee who later moves to another branch stays on old orders: names are
stored on the service and the order, so screens and reports keep showing them
and nothing blocks saving those orders.
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class WofHrEmployeeTechnician(models.Model):
    _inherit = 'hr.employee'

    is_wof_technician = fields.Boolean(
        string='فني تركيب', tracking=True,
        help='يظهر الموظف في قائمة فنيي خدمات أوامر التركيب لفرعه (شركته).',
    )
    is_wof_supervisor = fields.Boolean(
        string='مشرف تشغيل', tracking=True,
        help='يظهر الموظف في قائمة مشرفي التشغيل لأوامر تركيب فرعه.',
    )


class WofInstallationOrderLineTeam(models.Model):
    _inherit = 'wof.installation.order.line'

    technician_ids = fields.Many2many(
        'hr.employee', 'wof_order_line_technician_rel', 'line_id', 'employee_id',
        string='الفنيون', copy=False,
        domain="[('is_wof_technician', '=', True), ('company_id', 'in', [company_id, False])]",
        help='الفنيون الذين نفّذوا هذا المكوّن. يظهر فنيو فرع الأمر فقط.',
    )
    # compute_sudo: the stored names keep every technician, including one who
    # moved to a branch the current user cannot see.
    technician_names = fields.Char(
        string='أسماء الفنيين', compute='_compute_technician_names', store=True, compute_sudo=True,
    )

    @api.depends('technician_ids.name')
    def _compute_technician_names(self):
        # Read the relation itself: the ORM value is filtered by the branch rules
        # of the current user and would drop a technician who moved away.
        names = {}
        real = self.filtered('id')
        if real:
            self.env['wof.installation.order.line'].flush_model(['technician_ids'])
            self.env['hr.employee'].flush_model(['name'])
            self.env.cr.execute("""
                SELECT rel.line_id, emp.name FROM wof_order_line_technician_rel rel
                JOIN hr_employee emp ON emp.id = rel.employee_id
                WHERE rel.line_id IN %s ORDER BY rel.line_id, emp.id
            """, (tuple(real.ids),))
            for line_id, name in self.env.cr.fetchall():
                names.setdefault(line_id, []).append(name)
        for line in self:
            found = names.get(line.id) if line.id else line.technician_ids.mapped('name')
            line.technician_names = '، '.join(n for n in (found or []) if n) or False

    @api.model
    def _wof_team_ids_after(self, before, commands):
        """Employee ids a service will have after ``commands`` (and the ones added)."""
        final = set(before)
        for command in commands or []:
            code = command[0]
            if code == 4:
                final.add(command[1])
            elif code == 3:
                final.discard(command[1])
            elif code == 5:
                final = set()
            elif code == 6:
                final = set(command[2] or [])
        return final, final - set(before)

    def _wof_check_new_technicians(self, added, counts=None):
        """Technicians being added must be flagged and belong to the order's branch."""
        if not added or self.env.context.get('wof_skip_technician_check'):
            return
        Employee = self.env['hr.employee']
        profile = self.env['wof.company.profile']._wof_get_profile()
        for line, employee_ids in added.items():
            for employee_id in employee_ids:
                if not Employee.search_count([
                    ('id', '=', employee_id), ('is_wof_technician', '=', True),
                    ('company_id', 'in', [line.order_id.company_id.id, False]),
                ]):
                    raise ValidationError(_(
                        'الموظف المختار ليس فني تركيب في فرع هذا الأمر. اختر من فنيي الفرع المعلَّمين «فني تركيب».'))
            count = (counts or {}).get(line, len(employee_ids))
            if profile and not profile.operation_allow_multiple_technicians and count > 1:
                raise ValidationError(_('الإعدادات تسمح بفني واحد لكل خدمة (%s).') % line.display_name)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('technician_ids') and vals.get('order_id'):
                final, _added = self._wof_team_ids_after([], vals['technician_ids'])
                line = self.new({'order_id': vals['order_id']})
                self._wof_check_new_technicians({line: final}, {line: len(final)})
        return super().create(vals_list)

    def write(self, vals):
        if 'technician_ids' in vals:
            added, counts = {}, {}
            for line in self:
                final, new = self._wof_team_ids_after(line.technician_ids.ids, vals['technician_ids'])
                if new:
                    added[line], counts[line] = new, len(final)
            self._wof_check_new_technicians(added, counts)
        return super().write(vals)


class WofInstallationOrderTeam(models.Model):
    _inherit = 'wof.installation.order'

    technician_names = fields.Char(
        string='أسماء الفنيين', compute='_compute_technician_names', store=True, compute_sudo=True,
    )
    amount_gross = fields.Monetary(string='قيمة الخدمات', compute='_compute_order_summary')
    service_count = fields.Integer(string='عدد الخدمات', compute='_compute_order_summary')
    wof_paid_percent = fields.Float(string='نسبة المدفوع', compute='_compute_order_summary')
    salesman_candidate_ids = fields.Many2many('salesman', compute='_compute_salesman_candidates')

    @api.depends('line_ids.technician_names')
    def _compute_technician_names(self):
        for order in self:
            names = []
            for line_names in order.line_ids.mapped('technician_names'):
                for name in (line_names or '').split('، '):
                    if name and name not in names:
                        names.append(name)
            order.technician_names = '، '.join(names) or False

    @api.depends('amount_untaxed', 'amount_discount', 'line_ids', 'amount_total', 'amount_paid')
    def _compute_order_summary(self):
        for order in self:
            order.amount_gross = order.amount_untaxed + order.amount_discount
            order.service_count = len(order.line_ids)
            order.wof_paid_percent = min(100.0, order.amount_paid * 100.0 / order.amount_total) \
                if order.amount_total > 0 else 0.0

    # ------------------------------------------------------------- salesman
    @api.model
    def _wof_branch_salesmen(self, company):
        """Salesmen of a branch: their current assignment, else their own company."""
        Salesman = self.env['salesman']
        if not company:
            return Salesman
        current = self.env['salesman.assignments'].search([('state', '=', 'current')])
        assigned_here = current.filtered(lambda rec: rec.company_id == company).salesman_id
        assigned_elsewhere = current.filtered(lambda rec: rec.company_id != company).salesman_id
        own = Salesman.search([('company_id', '=', company.id)]) - assigned_elsewhere
        return assigned_here | own

    @api.depends('company_id')
    def _compute_salesman_candidates(self):
        for order in self:
            order.salesman_candidate_ids = order._wof_branch_salesmen(order.company_id)

    @api.model
    def _wof_default_salesman(self):
        salesmen = self._wof_branch_salesmen(self.env.company)
        return salesmen.filtered(lambda rec: rec.sale_user == self.env.user)[:1]

    @api.model
    def _wof_default_advisor(self):
        employees = self.env.user.employee_ids
        return employees.filtered(lambda emp: emp.company_id == self.env.company)[:1] or employees[:1]

    # --------------------------------------------------------------- people
    def _wof_is_assigned_technician(self, user=None):
        self.ensure_one()
        return (user or self.env.user) in self.line_ids.technician_ids.user_id

    def _wof_check_people(self, vals):
        """Check people only when they are chosen (never on later reads or moves)."""
        Employee = self.env['hr.employee']
        for order in self:
            company = order.company_id
            if vals.get('advisor_id') and not Employee.search_count([
                    ('id', '=', vals['advisor_id']), ('company_id', 'in', [company.id, False])]):
                raise ValidationError(_('مستشار الخدمة يجب أن يكون من موظفي فرع الأمر.'))
            if vals.get('supervisor_id') and not Employee.search_count([
                    ('id', '=', vals['supervisor_id']), ('is_wof_supervisor', '=', True),
                    ('company_id', 'in', [company.id, False])]):
                raise ValidationError(_('مشرف التشغيل يجب أن يكون من موظفي فرع الأمر المعلَّمين «مشرف تشغيل».'))
            if vals.get('salesperson_id') and vals['salesperson_id'] not in order._wof_branch_salesmen(company).ids:
                raise ValidationError(_('المندوب المختار غير مسند لفرع هذا الأمر.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'advisor_id' not in vals:
                vals['advisor_id'] = self._wof_default_advisor().id
            if 'salesperson_id' not in vals or not self._wof_can_change_salesman():
                vals['salesperson_id'] = self._wof_default_salesman().id
        orders = super().create(vals_list)
        for order, vals in zip(orders, vals_list):
            order._wof_check_people(vals)
        return orders

    # ---------------------------------------------------------------- branch
    @api.onchange('company_id')
    def _onchange_wof_branch(self):
        Employee = self.env['hr.employee']
        company = self.company_id
        for key in ('advisor_id', 'supervisor_id'):
            person = self[key]
            if person and not Employee.search_count([('id', '=', person.id), ('company_id', 'in', [company.id, False])]):
                self[key] = False
        if self.salesperson_id and self.salesperson_id not in self._wof_branch_salesmen(company):
            self.salesperson_id = False
        if not self.advisor_id:
            employees = self.env.user.employee_ids
            self.advisor_id = employees.filtered(lambda emp: emp.company_id == company)[:1]

    def _wof_can_change_salesman(self):
        return self.env.user.has_group('yousentech_invoicing_saleman.allow_modify_salesman')

    def write(self, vals):
        if 'salesperson_id' in vals and not self.env.su and not self._wof_can_change_salesman():
            if any(order.salesperson_id.id != vals['salesperson_id'] for order in self):
                raise ValidationError(_('تغيير المندوب يحتاج صلاحية «Allow Modify Salesman».'))
        changing = self.browse()
        if 'company_id' in vals:
            company = self.env['res.company'].browse(vals['company_id']).exists()
            changing = self.filtered(lambda order: order.company_id != company)
            if changing and not self.env.su and not self.env.user.has_group('yousentech_wo_v4.group_wo_change_branch'):
                raise ValidationError(_('تغيير فرع أمر التركيب يحتاج صلاحية «تغيير فرع أمر التركيب».'))
            if changing and (not company or company not in self.env.companies):
                raise ValidationError(_('اختر فرعًا من الفروع المسموح لك بالعمل عليها.'))
            for order in changing:
                if order.state not in ('draft', 'scheduled'):
                    raise ValidationError(_('يُغيَّر فرع الأمر قبل إكمال الاستلام فقط.'))
                paid = self.env['account.payment'].search_count([('wof_order_id', '=', order.id)]) \
                    if self.env['account.payment'].check_access_rights('read', raise_exception=False) else 0
                if paid or order.sale_order_id or order.invoice_id:
                    raise ValidationError(_('لا يمكن تغيير الفرع بعد تسجيل دفعات أو إنشاء أمر بيع أو فاتورة.'))
        result = super().write(vals)
        if {'advisor_id', 'supervisor_id', 'salesperson_id'} & set(vals):
            self._wof_check_people(vals)
        Employee = self.env['hr.employee']
        for order in changing:
            outside = order.line_ids.technician_ids.filtered(lambda emp: not Employee.search_count([
                ('id', '=', emp.id), ('company_id', 'in', [order.company_id.id, False])]))
            if outside:
                raise ValidationError(_('فنيو الخدمات التالية من فرع آخر، أزلهم أولًا: %s.')
                                      % '، '.join(outside.mapped('name')))
        return result
