# -*- coding: utf-8 -*-
"""Order screen sections and the stage buttons kept in step.

The setup decides which optional sections the order screen shows. A stage whose
section is hidden must still move with the header buttons, without asking for
what the user cannot see:

* execution hidden  → «إنهاء التنفيذ» completes the services (and technicians'
  tasks) itself; only the technicians are still required;
* quality & delivery hidden → finishing the work approves quality at once (the
  order becomes «جاهز للتسليم») and delivery records the customer's approval.

A technician (without reception / supervisor rights) sees the execution screen
only, with the customer and car summary on top.
"""

from odoo import api, fields, models, _
from odoo.exceptions import AccessError

OPTIONAL_SECTIONS = ('intake', 'execution', 'quality', 'attachments', 'timeline', 'extras')


class WofOrderSections(models.Model):
    _inherit = 'wof.installation.order'

    wof_technician_view = fields.Boolean(compute='_compute_wof_field_policy')
    wof_quality_enabled = fields.Boolean(compute='_compute_wof_field_policy')

    def _compute_wof_field_policy(self):
        super()._compute_wof_field_policy()
        technician_only = self._wof_technician_only()
        quality = self._wof_section_enabled('quality')
        for order in self:
            order.wof_technician_view = technician_only
            order.wof_quality_enabled = quality
            if technician_only:
                order.wof_ui_sections = ',execution,'

    @api.model
    def _wof_technician_only(self):
        user = self.env.user
        return user.has_group('yousentech_wo_v4.group_wo_technician') and not any(
            user.has_group(group) for group in (
                'yousentech_wo_v4.group_wo_user', 'yousentech_wo_v4.group_wo_supervisor',
                'yousentech_wo_v4.group_wo_manager'))

    @api.model
    def _wof_section_enabled(self, key):
        """Is the optional section ``key`` switched on in the setup (for everyone)?"""
        profile = self.env['wof.company.profile']._wof_get_profile()
        return bool(profile and profile['ui_%s' % key])

    @api.model
    def open_main_menu(self):
        # A technician's home is his touch screen of tasks.
        if self._wof_technician_only():
            self._ensure_setup_is_ready()
            return self.env['ir.actions.actions']._for_xml_id('yousentech_wo_v4.action_wof_my_tasks_screen')
        return super().open_main_menu()

    def _wof_refuse_technician(self, what):
        if self._wof_technician_only():
            raise AccessError(_('%s ليس من صلاحية الفني؛ يقوم به الاستقبال أو المشرف.') % what)

    def action_register_payment(self):
        self._wof_refuse_technician(_('تسجيل الدفعات'))
        return super().action_register_payment()

    def action_create_invoice(self):
        self._wof_refuse_technician(_('إنشاء الفاتورة'))
        return super().action_create_invoice()

    def action_create_sale_order(self):
        self._wof_refuse_technician(_('إنشاء أمر البيع'))
        return super().action_create_sale_order()

    # ------------------------------------------------------------ stages
    def action_submit_quality(self):
        self.ensure_one()
        order = self
        if not self._wof_section_enabled('execution'):
            self._wof_complete_execution_silently()
            order = self.with_context(wof_quality_no_wizard=True)
        result = super(WofOrderSections, order).action_submit_quality()
        if self.state == 'quality' and not self._wof_section_enabled('quality'):
            # No quality screen: the end of the work is the quality approval.
            self._perform_transition('quality', 'ready', 'order.quality_passed', {
                'quality_passed': True,
                'quality_checked_at': fields.Datetime.now(),
                'quality_checked_by_id': self.env.user.id,
            })
        return result

    def _wof_complete_execution_silently(self):
        """Without the execution screen the services are complete when the work ends
        (technicians are still checked by the stage)."""
        need_technician = self._wof_field_required('technician')
        if need_technician and self.line_ids.filtered(lambda line: not line.technician_names):
            return  # the stage explains which services still need technicians
        self.task_ids.filtered(lambda task: not task.done).with_context(wof_task_internal=True).write({
            'done': True, 'done_at': fields.Datetime.now(), 'done_by_id': self.env.user.id})
        for line in self.line_ids.filtered(lambda rec: rec.execution_progress != 100):
            if line.part_line_ids:
                line.part_line_ids.filtered(lambda part: part.progress != 100).with_context(
                    wof_part_internal=True).write({'progress': 100})
            else:
                line._write_line_internal({'execution_progress': 100})

    def action_pass_quality(self):
        self.ensure_one()
        if not self._wof_section_enabled('quality') and not self.quality_passed:
            self._transition_write({'quality_passed': True})
        return super().action_pass_quality()

    def action_deliver(self):
        self.ensure_one()
        if not self._wof_section_enabled('quality') and not self.customer_approved:
            # The approval is the handover itself when there is no delivery screen.
            self._transition_write({'customer_approved': True, 'customer_approval_at': fields.Datetime.now()})
        return super().action_deliver()
