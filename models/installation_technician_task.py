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
    employee_name = fields.Char(string='الفني', readonly=True)
    employee_user_id = fields.Many2one('res.users', string='مستخدم الفني', readonly=True)
    service_label = fields.Char(string='الخدمة / الجزء', compute='_compute_service_label')
    done = fields.Boolean(string='اكتمل', default=False)
    done_at = fields.Datetime(string='وقت الإكمال', readonly=True)
    done_by_id = fields.Many2one('res.users', string='سجّله', readonly=True)

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
            new = [{'line_id': line.id, 'part_id': part_id, 'employee_id': emp, 'employee_name': name,
                    'employee_user_id': user_id} for (part_id, emp), (name, user_id) in wanted.items()
                   if (part_id, emp) not in have]
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
