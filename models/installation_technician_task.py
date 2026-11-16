# -*- coding: utf-8 -*-
"""What each technician has to finish (مهام الفنيين).

One task per technician on a service — or on each part of a service area. Tasks
follow the technicians assigned on the service card: added and removed with
them. A technician marks his own task done during the work (reception and
supervisors may mark any); the service's (or part's) progress is then the share
of its finished tasks, so «60%» means three of five tasks are done.
"""

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class WofTechnicianTask(models.Model):
    _name = 'wof.technician.task'
    _description = 'مهمة فني في أمر التركيب'
    _order = 'order_id, line_id, part_id, id'

    line_id = fields.Many2one('wof.installation.order.line', string='الخدمة', required=True,
                              ondelete='cascade', index=True)
    part_id = fields.Many2one('wof.installation.order.line.part', string='الجزء', ondelete='cascade', index=True)
    order_id = fields.Many2one(related='line_id.order_id', store=True, index=True, string='أمر التركيب')
    company_id = fields.Many2one(related='line_id.order_id.company_id', store=True, string='الفرع')
    order_state = fields.Selection(related='line_id.order_id.state', string='حالة الأمر')
    employee_id = fields.Many2one('hr.employee', string='الفني', required=True, ondelete='cascade', index=True)
    # Follow the employee card (a technician's user may be linked or changed later).
    employee_name = fields.Char(related='employee_id.name', store=True, string='الفني')
    employee_user_id = fields.Many2one(related='employee_id.user_id', store=True, string='مستخدم الفني', index=True)
    service_label = fields.Char(string='الخدمة / الجزء', compute='_compute_service_label')
    done = fields.Boolean(string='اكتمل', default=False)
    done_at = fields.Datetime(string='وقت الإكمال', readonly=True)
    done_by_id = fields.Many2one('res.users', string='سجّله', readonly=True)
    status = fields.Selection([
        ('waiting', 'بانتظار التنفيذ'), ('open', 'قيد العمل'), ('done', 'مكتملة'),
    ], string='الحالة', compute='_compute_status', store=True, group_expand='_expand_status')
    # Card details (read through the order the technician is assigned to).
    order_name = fields.Char(related='line_id.order_id.name', string='رقم الأمر')
    vehicle_plate = fields.Char(related='line_id.order_id.vehicle_plate', string='اللوحة')
    vehicle_manufacturer_id = fields.Many2one(related='line_id.order_id.vehicle_manufacturer_id', string='الماركة')
    vehicle_model_id = fields.Many2one(related='line_id.order_id.vehicle_model_id', string='الموديل')
    vehicle_color_id = fields.Many2one(related='line_id.order_id.vehicle_color_id', string='اللون')
    film_name = fields.Char(related='line_id.film_category_id.name', string='الفيلم')
    grade_name = fields.Char(compute='_compute_grade_name', string='الدرجة')
    appointment_at = fields.Date(related='line_id.order_id.appointment_at', store=True, string='تاريخ الأمر')
    deadline = fields.Datetime(related='line_id.order_id.expected_delivery_at', store=True, string='موعد التسليم')
    is_late = fields.Boolean(compute='_compute_is_late', string='متأخرة')
    is_mine = fields.Boolean(compute='_compute_is_mine', string='مهمتي')

    @api.model
    def _expand_status(self, states, domain, order):
        return [key for key, _label in self._fields['status'].selection]

    @api.depends('done', 'line_id.order_id.state')
    def _compute_status(self):
        for task in self:
            if task.done:
                task.status = 'done'
            elif task.line_id.order_id.state == 'in_progress':
                task.status = 'open'
            else:
                task.status = 'waiting'

    @api.depends('part_id.grade_id', 'line_id.film_category_line_id')
    def _compute_grade_name(self):
        for task in self:
            grade = task.part_id.grade_id if task.part_id else task.line_id.film_category_line_id
            task.grade_name = grade.display_name or ''

    def _compute_is_late(self):
        now = fields.Datetime.now()
        for task in self:
            task.is_late = bool(not task.done and task.deadline and task.deadline < now)

    def _compute_is_mine(self):
        for task in self:
            task.is_mine = task.employee_user_id == self.env.user

    # ------------------------------------------------------------ actions
    def action_mark_done(self):
        self.filtered(lambda task: not task.done).write({'done': True})
        return True

    def action_mark_open(self):
        self.filtered('done').write({'done': False})
        return True

    def action_open_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'res_model': 'wof.installation.order', 'view_mode': 'form',
            'res_id': self.order_id.id, 'target': 'current',
        }

    _sql_constraints = [
        ('task_unique', 'unique(line_id, part_id, employee_id)', 'للفني مهمة واحدة على كل خدمة أو جزء.'),
    ]

    @api.depends('line_id.car_part_id', 'part_id.part_id')
    def _compute_service_label(self):
        for task in self:
            label = task.line_id.car_part_id.name or ''
            if task.part_id:
                label = '%s / %s' % (label, task.part_id.part_id.name or '')
            task.service_label = label

    def write(self, vals):
        if 'done' in vals and not self.env.context.get('wof_task_internal'):
            lead = self.env['wof.installation.order.line']._wof_is_team_lead()
            for task in self:
                if task.order_state != 'in_progress':
                    raise ValidationError(_('تُسجَّل المهام أثناء «قيد التنفيذ» فقط.'))
                if not lead and task.employee_user_id != self.env.user:
                    raise AccessError(_('يسجّل الفني إكمال مهامه فقط.'))
            vals = dict(vals, done_at=fields.Datetime.now() if vals['done'] else False,
                        done_by_id=self.env.user.id if vals['done'] else False)
        result = super().write(vals)
        if 'done' in vals:
            self._wof_push_progress()
        return result

    def _wof_push_progress(self):
        """Progress of the parts / services of these tasks = share of finished tasks."""
        Task = self.env['wof.technician.task']
        for part in self.part_id:
            tasks = Task.search([('part_id', '=', part.id)])
            progress = round(100 * len(tasks.filtered('done')) / len(tasks)) if tasks else 0
            if part.progress != progress:
                part.with_context(wof_part_internal=True).write({'progress': progress})
        for line in self.filtered(lambda task: not task.part_id).line_id:
            tasks = Task.search([('line_id', '=', line.id), ('part_id', '=', False)])
            progress = round(100 * len(tasks.filtered('done')) / len(tasks)) if tasks else 0
            if line.execution_progress != progress:
                line._write_line_internal({'execution_progress': progress})


class WofOrderLineTasks(models.Model):
    _inherit = 'wof.installation.order.line'

    task_ids = fields.One2many('wof.technician.task', 'line_id', string='مهام الفنيين')

    def _wof_assigned(self, table, column, record_id):
        self.env.cr.execute('SELECT r.employee_id, e.name, e.user_id FROM %s r JOIN hr_employee e ON e.id = r.employee_id '
                            'WHERE r.%s = %%s' % (table, column), (record_id,))
        return {row[0]: (row[1], row[2]) for row in self.env.cr.fetchall()}

    def _wof_sync_tasks(self):
        """Tasks follow the assigned technicians (per part for service areas)."""
        Task = self.env['wof.technician.task'].with_context(wof_task_internal=True)
        self.env['wof.installation.order.line'].flush_model(['technician_ids'])
        self.env['wof.installation.order.line.part'].flush_model(['technician_ids'])
        self.env['hr.employee'].flush_model(['name', 'user_id'])
        for line in self:
            wanted = {}
            if line.part_line_ids:
                for part in line.part_line_ids:
                    for emp, info in line._wof_assigned('wof_order_line_part_technician_rel', 'part_line_id', part.id).items():
                        wanted[(part.id, emp)] = info
            else:
                for emp, info in line._wof_assigned('wof_order_line_technician_rel', 'line_id', line.id).items():
                    wanted[(False, emp)] = info
            current = Task.search([('line_id', '=', line.id)])
            have = {(task.part_id.id or False, task.employee_id.id): task for task in current}
            (current - Task.browse([task.id for key, task in have.items() if key in wanted])).unlink()
            new = [{'line_id': line.id, 'part_id': part_id, 'employee_id': emp}
                   for (part_id, emp) in wanted if (part_id, emp) not in have]
            if new:
                Task.create(new)

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._wof_sync_tasks()
        return lines

    def write(self, vals):
        result = super().write(vals)
        if 'technician_ids' in vals or 'service_area_template_id' in vals or 'car_part_id' in vals:
            self._wof_sync_tasks()
        return result


class WofOrderLinePartTasks(models.Model):
    _inherit = 'wof.installation.order.line.part'

    def write(self, vals):
        result = super().write(vals)
        if 'technician_ids' in vals:
            self.line_id._wof_sync_tasks()
        return result

    @api.model_create_multi
    def create(self, vals_list):
        parts = super().create(vals_list)
        parts.line_id._wof_sync_tasks()
        return parts


class WofOrderTasks(models.Model):
    _inherit = 'wof.installation.order'

    task_ids = fields.One2many('wof.technician.task', 'order_id', string='مهام الفنيين')
    # The technician's own tasks (the technician view of the order shows these only).
    my_task_ids = fields.One2many('wof.technician.task', 'order_id', string='مهامي',
                                  domain=lambda self: [('employee_user_id', '=', self.env.uid)])
    task_done_count = fields.Integer(compute='_compute_task_counts')
    task_count = fields.Integer(compute='_compute_task_counts')

    @api.depends('task_ids.done')
    def _compute_task_counts(self):
        for order in self:
            order.task_count = len(order.task_ids)
            order.task_done_count = len(order.task_ids.filtered('done'))


class WofMyTasksScreen(models.Model):
    """Data of the technician's touch screen «مهامي»: his tasks grouped by car."""
    _inherit = 'wof.technician.task'

    @api.model
    def wof_my_tasks_load(self):
        user = self.env.user
        today = fields.Datetime.to_string(fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0))
        tasks = self.search([
            ('employee_user_id', '=', user.id),
            '|', ('order_id.state', 'in', ('draft', 'scheduled', 'intake', 'in_progress')),
                 ('done_at', '>=', today),
        ])
        states = dict(self.env['wof.installation.order']._fields['state']._description_selection(self.env))
        groups = {'now': [], 'next': [], 'done': []}
        for order in tasks.order_id.sorted(lambda rec: (rec.expected_delivery_at or rec.create_date, rec.id)):
            mine = tasks.filtered(lambda task: task.order_id == order)
            if order.state == 'in_progress':
                bucket = 'done' if all(mine.mapped('done')) else 'now'
            elif order.state in ('draft', 'scheduled', 'intake'):
                bucket = 'next'
            else:
                bucket = 'done'
            car = ' '.join(filter(None, [order.vehicle_manufacturer_id.name, order.vehicle_model_id.name]))
            groups[bucket].append({
                'id': order.id, 'name': order.name, 'plate': order.vehicle_plate or '', 'car': car,
                'color': order.vehicle_color_id.name or '', 'size': order.car_size_id.name or '',
                'state': order.state, 'state_label': states.get(order.state, ''),
                'team': order.technician_names or '',
                'deadline': fields.Datetime.to_string(order.expected_delivery_at) if order.expected_delivery_at else False,
                'late': bool(order.state == 'in_progress' and order.expected_delivery_at
                             and order.expected_delivery_at < fields.Datetime.now() and not all(mine.mapped('done'))),
                'can_work': order.state == 'in_progress',
                'done_count': len(mine.filtered('done')), 'total': len(mine),
                'tasks': [{
                    'id': task.id, 'label': task.part_id.part_id.name or task.line_id.car_part_id.name or '',
                    'area': task.line_id.car_part_id.name if task.part_id else '',
                    'film': task.film_name or '', 'grade': task.grade_name or '', 'done': task.done,
                    'done_at': fields.Datetime.to_string(task.done_at) if task.done_at else False,
                } for task in mine.sorted(lambda task: (task.done, task.id))],
            })
        return {'user': user.name, 'groups': groups}

    def wof_my_task_set(self, done):
        """Mark one of the user's tasks done / not done from the touch screen."""
        self.ensure_one()
        self.write({'done': bool(done)})
        return self.wof_my_tasks_load()
