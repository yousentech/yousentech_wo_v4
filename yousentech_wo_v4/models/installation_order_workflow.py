# -*- coding: utf-8 -*-

import json

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

from .api_foundation import OPERATION_SOURCE_TOKEN, _trusted_operation_source
from .installation_order import (
    EVENT_LABELS,
    ORDER_EVENT_TOKEN,
    ORDER_STATES,
    ORDER_TRANSITION_TOKEN,
)


class WofInstallationOrderWorkflow(models.Model):
    _inherit = 'wof.installation.order'

    def _profile(self):
        self.ensure_one()
        return self._ensure_company_is_ready(self.company_id)

    def _ensure_role(self, *group_xmlids):
        if not any(self.env.user.has_group(group) for group in group_xmlids):
            raise AccessError(
                _('لا تملك الصلاحية المطلوبة لتنفيذ هذه الخطوة.')
            )

    def _ensure_assigned_technician_or_supervisor(self):
        self.ensure_one()
        is_supervisor = any(
            self.env.user.has_group(group)
            for group in (
                'yousentech_wo_v4.group_wo_supervisor',
                'yousentech_wo_v4.group_wo_manager',
            )
        )
        if not is_supervisor and self.env.user not in self.technician_ids:
            raise AccessError(
                'يمكن للفني تنفيذ الإجراءات على الأوامر المسندة إليه فقط.'
            )

    def write(self, vals):
        vals = dict(vals)
        if 'vehicle_plate' in vals:
            vals['vehicle_plate'] = (vals['vehicle_plate'] or '').strip().upper()
        if 'vehicle_vin' in vals and vals['vehicle_vin']:
            vals['vehicle_vin'] = vals['vehicle_vin'].strip().upper()
        protected = {
            'name',
            'state',
            'company_id',
            'created_by_id',
            'idempotency_key',
            'idempotency_fingerprint',
            'arrival_confirmed_at',
            'intake_completed_at',
            'execution_started_at',
            'execution_completed_at',
            'quality_checked_at',
            'quality_checked_by_id',
            'delivered_at',
            'delivered_by_id',
            'cancelled_at',
            'cancelled_by_id',
            'customer_approval_at',
            'discount_scope',
            'use_appointments',
            'sale_order_id',
            'invoice_id',
            'warranty_status',
            'warranty_reference',
        }
        if (
            protected.intersection(vals)
            and self.env.context.get('wof_order_transition_token')
            is not ORDER_TRANSITION_TOKEN
        ):
            raise ValidationError(
                'استخدم إجراءات أمر التركيب المعتمدة لتغيير الحالة أو بيانات التدقيق.'
            )
        commercial = {
            'partner_id',
            'customer_notes',
            'vehicle_plate',
            'vehicle_vin',
            'vehicle_manufacturer_id',
            'vehicle_model_id',
            'vehicle_year_id',
            'vehicle_color',
            'car_size_id',
            'appointment_at',
            'expected_delivery_at',
            'advisor_id',
            'supervisor_id',
            'technician_ids',
            'line_ids',
            'order_discount_percent',
        }
        intake_fields = {
            'odometer',
            'intake_condition',
            'intake_notes',
            'before_attachment_ids',
        }
        execution_fields = {
            'execution_notes',
            'after_attachment_ids',
            'material_line_ids',
        }
        quality_fields = {'quality_passed', 'quality_notes'}
        delivery_fields = {
            'customer_approved',
            'customer_approval_reference',
            'delivery_notes',
        }
        for order in self:
            if commercial.intersection(vals):
                order._ensure_role(
                    'yousentech_wo_v4.group_wo_user',
                    'yousentech_wo_v4.group_wo_supervisor',
                    'yousentech_wo_v4.group_wo_manager',
                )
                staff_only = {'supervisor_id', 'technician_ids'}
                non_staff_fields = commercial - staff_only
                if non_staff_fields.intersection(vals) and order.state not in {
                    'draft',
                    'scheduled',
                }:
                    raise ValidationError(
                        'لا يمكن تعديل بيانات العميل أو السيارة أو التسعير بعد إكمال الاستلام.'
                    )
                if staff_only.intersection(vals) and order.state not in {
                    'draft',
                    'scheduled',
                    'intake',
                    'in_progress',
                }:
                    raise ValidationError(
                        'لا يمكن تغيير فريق العمل بعد إرسال الأمر إلى فحص الجودة.'
                    )
            if (
                intake_fields.intersection(vals)
                and self.env.context.get('wof_order_transition_token')
                is not ORDER_TRANSITION_TOKEN
            ):
                order._ensure_role(
                    'yousentech_wo_v4.group_wo_user',
                    'yousentech_wo_v4.group_wo_supervisor',
                    'yousentech_wo_v4.group_wo_manager',
                )
                if order.state not in {'draft', 'scheduled'}:
                    raise ValidationError(
                        'بيانات فحص الاستلام تعدل قبل إكمال مرحلة الاستلام فقط.'
                    )
            if (
                execution_fields.intersection(vals)
                and self.env.context.get('wof_order_transition_token')
                is not ORDER_TRANSITION_TOKEN
            ):
                order._ensure_role(
                    'yousentech_wo_v4.group_wo_technician',
                    'yousentech_wo_v4.group_wo_supervisor',
                    'yousentech_wo_v4.group_wo_manager',
                )
                if order.state not in {'in_progress', 'quality'}:
                    raise ValidationError(
                        'ملاحظات ومرفقات التنفيذ تعدل أثناء التنفيذ أو فحص الجودة فقط.'
                    )
                is_supervisor = any(
                    self.env.user.has_group(group)
                    for group in (
                        'yousentech_wo_v4.group_wo_supervisor',
                        'yousentech_wo_v4.group_wo_manager',
                    )
                )
                if not is_supervisor and self.env.user not in order.technician_ids:
                    raise AccessError(
                        'يمكن للفني تحديث أوامر التركيب المسندة إليه فقط.'
                    )
            if (
                quality_fields.intersection(vals)
                and self.env.context.get('wof_order_transition_token')
                is not ORDER_TRANSITION_TOKEN
            ):
                order._ensure_role(
                    'yousentech_wo_v4.group_wo_supervisor',
                    'yousentech_wo_v4.group_wo_manager',
                )
                if order.state != 'quality':
                    raise ValidationError(
                        'نتيجة الجودة تعدل في مرحلة فحص الجودة فقط.'
                    )
            if (
                delivery_fields.intersection(vals)
                and self.env.context.get('wof_order_transition_token')
                is not ORDER_TRANSITION_TOKEN
            ):
                order._ensure_role(
                    'yousentech_wo_v4.group_wo_user',
                    'yousentech_wo_v4.group_wo_supervisor',
                    'yousentech_wo_v4.group_wo_manager',
                )
                if order.state != 'ready':
                    raise ValidationError(
                        'موافقة العميل وبيانات التسليم تعدل عندما تصبح السيارة جاهزة.'
                    )
            if 'cancellation_reason' in vals:
                order._ensure_role(
                    'yousentech_wo_v4.group_wo_supervisor',
                    'yousentech_wo_v4.group_wo_manager',
                )
                if order.state == 'cancelled':
                    raise ValidationError(
                        'سبب الإلغاء جزء من سجل التدقيق ولا يمكن تغييره بعد الإلغاء.'
                    )
            if 'active' in vals and vals['active'] != order.active:
                order._ensure_role('yousentech_wo_v4.group_wo_manager')
                if order.state not in {'delivered', 'cancelled'}:
                    raise ValidationError(
                        'يمكن أرشفة أمر التركيب بعد التسليم أو الإلغاء فقط.'
                    )
        result = super().write(vals)
        if 'car_size_id' in vals:
            for order in self:
                order.line_ids._refresh_pricing()
        return result

    def unlink(self):
        raise UserError(
            'لا يمكن حذف أوامر التركيب. ألغِ الأمر بسبب واضح ثم أرشفه عند الحاجة.'
        )

    def _transition_write(self, values):
        return self.with_context(
            wof_order_transition_token=ORDER_TRANSITION_TOKEN
        ).write(values)

    def _log_business_event(
        self,
        event_code,
        from_state=None,
        to_state=None,
        note=None,
        details=None,
    ):
        self.ensure_one()
        if event_code not in EVENT_LABELS:
            raise ValidationError('رمز حدث أمر التركيب غير معروف.')
        source = _trusted_operation_source(self.env)
        event_env = self.env['wof.installation.order.event'].with_context(
            wof_order_event_token=ORDER_EVENT_TOKEN,
            wof_operation_source=source,
            wof_operation_source_token=OPERATION_SOURCE_TOKEN,
        )
        # This sudo is narrowly limited to an append-only event row after
        # the caller has already passed order ACL, company, role and state checks.
        event_env.sudo().create({
            'order_id': self.id,
            'event_code': event_code,
            'event_label': EVENT_LABELS[event_code],
            'from_state': from_state,
            'to_state': to_state,
            'user_id': self.env.user.id,
            'note': note,
            'details_json': json.dumps(
                details or {}, ensure_ascii=False, default=str
            ),
        })
        self._audit_event(event_code, {
            'from_state': from_state,
            'to_state': to_state,
            'note': note,
            **(details or {}),
        })

    def _perform_transition(self, expected_state, target_state, event_code, values=None):
        self.ensure_one()
        if self.state != expected_state:
            raise ValidationError(
                'لا يمكن تنفيذ هذه الخطوة من الحالة الحالية (%s).'
                % dict(ORDER_STATES)[self.state]
            )
        previous = self.state
        transition_values = dict(values or {}, state=target_state)
        self._transition_write(transition_values)
        self._log_business_event(
            event_code,
            from_state=previous,
            to_state=target_state,
        )
        return True

    def _validate_order_basics(self):
        self.ensure_one()
        profile = self._profile()
        missing = []
        if not self.partner_id:
            missing.append('العميل')
        if not (self.partner_id.mobile or self.partner_id.phone):
            missing.append('جوال أو هاتف العميل')
        if not self.vehicle_plate:
            missing.append('رقم اللوحة')
        if profile.required_vehicle_data == 'plate_vin_mobile' and not self.vehicle_vin:
            missing.append('رقم الهيكل')
        if not self.car_size_id:
            missing.append('حجم السيارة')
        if profile.use_appointments and not self.appointment_at:
            missing.append('الموعد')
        if not self.line_ids:
            missing.append('خدمة واحدة على الأقل')
        if missing:
            raise ValidationError(
                'أكمل البيانات التالية قبل المتابعة: %s.'
                % '، '.join(missing)
            )
        self.line_ids._validate_ready_for_confirmation()

    def action_confirm_arrival(self):
        self.ensure_one()
        self._ensure_role(
            'yousentech_wo_v4.group_wo_user',
            'yousentech_wo_v4.group_wo_supervisor',
            'yousentech_wo_v4.group_wo_manager',
        )
        self._validate_order_basics()
        return self._perform_transition(
            'draft',
            'scheduled',
            'order.arrival_confirmed',
            {'arrival_confirmed_at': fields.Datetime.now()},
        )

    def action_complete_intake(self):
        self.ensure_one()
        self._ensure_role(
            'yousentech_wo_v4.group_wo_user',
            'yousentech_wo_v4.group_wo_supervisor',
            'yousentech_wo_v4.group_wo_manager',
        )
        if not self.intake_condition:
            raise ValidationError(
                'حدد حالة السيارة عند الاستلام قبل إكمال الفحص.'
            )
        if (
            self.intake_condition in {'existing_damage', 'needs_review'}
            and not (self.intake_notes or '').strip()
        ):
            raise ValidationError(
                'اكتب ملاحظة توضح الضرر السابق أو سبب المراجعة.'
            )
        return self._perform_transition(
            'scheduled',
            'intake',
            'order.intake_completed',
            {'intake_completed_at': fields.Datetime.now()},
        )

    def action_start_execution(self):
        self.ensure_one()
        self._ensure_role(
            'yousentech_wo_v4.group_wo_technician',
            'yousentech_wo_v4.group_wo_supervisor',
            'yousentech_wo_v4.group_wo_manager',
        )
        self._ensure_assigned_technician_or_supervisor()
        if not self.technician_ids:
            raise ValidationError(
                'عيّن فنيًا واحدًا على الأقل قبل بدء التنفيذ.'
            )
        if len(self.technician_ids) == 1:
            unassigned = self.line_ids.filtered(
                lambda line: not line.execution_technician_id
            )
            unassigned._write_line_internal({
                'execution_technician_id': self.technician_ids.id,
            })
        return self._perform_transition(
            'intake',
            'in_progress',
            'order.execution_started',
            {'execution_started_at': fields.Datetime.now()},
        )

    def action_submit_quality(self):
        self.ensure_one()
        self._ensure_role(
            'yousentech_wo_v4.group_wo_technician',
            'yousentech_wo_v4.group_wo_supervisor',
            'yousentech_wo_v4.group_wo_manager',
        )
        self._ensure_assigned_technician_or_supervisor()
        incomplete = self.line_ids.filtered(
            lambda line: (
                line.execution_progress != 100
                or not line.execution_technician_id
            )
        )
        if incomplete:
            raise ValidationError(
                'أكمل جميع الخدمات إلى 100٪ وحدد فني التنفيذ لكل خدمة قبل فحص الجودة.'
            )
        return self._perform_transition(
            'in_progress',
            'quality',
            'order.sent_to_quality',
            {'execution_completed_at': fields.Datetime.now()},
        )

    def action_return_to_execution(self):
        self.ensure_one()
        self._ensure_role(
            'yousentech_wo_v4.group_wo_supervisor',
            'yousentech_wo_v4.group_wo_manager',
        )
        if not (self.quality_notes or '').strip():
            raise ValidationError(
                'اكتب ملاحظة الجودة التي يجب معالجتها قبل إعادة التنفيذ.'
            )
        self._perform_transition(
            'quality',
            'in_progress',
            'order.quality_rejected',
            {'quality_passed': False},
        )
        return True

    def action_pass_quality(self):
        self.ensure_one()
        self._ensure_role(
            'yousentech_wo_v4.group_wo_supervisor',
            'yousentech_wo_v4.group_wo_manager',
        )
        if not self.quality_passed:
            raise ValidationError(
                'فعّل خيار «اجتاز فحص الجودة» قبل اعتماد الجاهزية.'
            )
        return self._perform_transition(
            'quality',
            'ready',
            'order.quality_passed',
            {
                'quality_checked_at': fields.Datetime.now(),
                'quality_checked_by_id': self.env.user.id,
            },
        )

    def action_deliver(self):
        self.ensure_one()
        self._ensure_role(
            'yousentech_wo_v4.group_wo_user',
            'yousentech_wo_v4.group_wo_supervisor',
            'yousentech_wo_v4.group_wo_manager',
        )
        if not self.customer_approved:
            raise ValidationError(
                'سجّل موافقة العميل على الأعمال والتسليم قبل إغلاق الأمر.'
            )
        now = fields.Datetime.now()
        return self._perform_transition(
            'ready',
            'delivered',
            'order.delivered',
            {
                'customer_approval_at': self.customer_approval_at or now,
                'delivered_at': now,
                'delivered_by_id': self.env.user.id,
            },
        )

    def action_cancel(self):
        self.ensure_one()
        self._ensure_role(
            'yousentech_wo_v4.group_wo_supervisor',
            'yousentech_wo_v4.group_wo_manager',
        )
        if self.state in {'delivered', 'cancelled'}:
            raise ValidationError(
                'لا يمكن إلغاء أمر تم تسليمه أو إلغاؤه مسبقًا.'
            )
        reason = (self.cancellation_reason or '').strip()
        if not reason:
            raise ValidationError(
                'اكتب سبب الإلغاء أولًا؛ لا يمكن إلغاء الأمر دون سبب.'
            )
        if self.invoice_id and self.invoice_id.state == 'posted':
            raise ValidationError(
                'لا يمكن إلغاء الأمر لوجود فاتورة مرحلة. عالج الفاتورة محاسبيًا أولًا.'
            )
        if self.sale_order_id and self.sale_order_id.state in {'sale', 'done'}:
            raise ValidationError(
                'لا يمكن إلغاء الأمر لوجود أمر بيع مؤكد. عالج أمر البيع أولًا.'
            )
        previous = self.state
        self._transition_write({
            'state': 'cancelled',
            'cancelled_at': fields.Datetime.now(),
            'cancelled_by_id': self.env.user.id,
        })
        self._log_business_event(
            'order.cancelled',
            from_state=previous,
            to_state='cancelled',
            note=reason,
        )
        return True

    def action_open_sale_order(self):
        self.ensure_one()
        if not self.sale_order_id:
            raise UserError('لا يوجد أمر بيع مرتبط حتى الآن.')
        return {
            'type': 'ir.actions.act_window',
            'name': _('أمر البيع'),
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.sale_order_id.id,
        }

    def action_open_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            raise UserError('لا توجد فاتورة مرتبطة حتى الآن.')
        return {
            'type': 'ir.actions.act_window',
            'name': _('الفاتورة'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.invoice_id.id,
        }

    @api.model
    def open_main_menu(self):
        company = self.env.company
        self._ensure_company_is_ready(company)
        return self.env.ref(
            'yousentech_wo_v4.action_wof_installation_order'
        ).read()[0]
