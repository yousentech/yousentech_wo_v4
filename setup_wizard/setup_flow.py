# -*- coding: utf-8 -*-
"""Service layer for the guided system-setup screen (OWL client action ``wof_setup_flow``).

The screen keeps no business rules of its own: every change goes through the
existing profile, line and dialog models, so validation, audit and locking rules
stay exactly where they were.
"""

from odoo import _, fields, models
from odoo.exceptions import ValidationError

from .setup_wizard import SETUP_STEPS, TECHNICAL_CODE_RE

FLOW_STEPS = dict(SETUP_STEPS)

FLOW_SCALARS = {
    'operation_tax_enabled': 'bool',
    'operation_tax_id': 'tax',
    'operation_pricing_policy': ('fixed', 'by_size'),
    'discount_enabled': 'bool',
    'discount_default_limit': 'percent',
    'discount_reason_required_from': 'percent',
    'discount_allow_override_request': 'bool',
    'discount_scope': ('order', 'service'),
    'operation_allow_multiple_technicians': 'bool',
    'commission_event': ('delivery', 'invoice'),
}


class WofCompanyProfileSetupFlow(models.Model):
    _inherit = 'wof.company.profile'

    # ------------------------------------------------------------------ entry
    def _wizard_action(self):
        """Every path that used to reopen the setup form now opens the guided screen."""
        self.ensure_one()
        self._wof_flow_prepare()
        return {
            'type': 'ir.actions.client',
            'tag': 'wof_setup_flow',
            'name': _('تهيئة النظام'),
            'target': 'new',
            'params': {'profile_id': self.id},
            'context': {'dialog_size': 'extra-large'},
        }

    def _wof_flow_prepare(self):
        self._ensure_default_activities()
        self._ensure_default_sizes()
        self._ensure_default_tint_shades()
        self._ensure_default_operation_fields()
        self._ensure_default_operation_tax()

    def action_go_to_activities(self):
        """After activation, continue on the films & services page."""
        self.ensure_one()
        self._ensure_can_configure()
        return self.env['wof.film.category'].action_open_films_hub()

    # --------------------------------------------------------------- snapshot
    def _wof_flow_taxes(self):
        return self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('active', '=', True),
        ])

    def _wof_flow_invoice_mode(self):
        if self.payment_policy == 'full_before_invoice':
            return 'after'
        return 'auto' if self.operation_auto_invoice else 'manual'

    def _wof_flow_snapshot(self):
        self.ensure_one()
        currency = self.env.company.currency_id
        return {
            'id': self.id,
            'state': self.state,
            'step': self.current_step,
            'applied': bool(self.completed_at),
            'currency': currency.symbol or currency.name or '',
            'activities': [{
                'id': line.id, 'name': line.name, 'description': line.description or '',
                'type': line.activity_type, 'selected': line.selected,
                'is_default': line.is_system_default,
            } for line in self.activity_line_ids],
            'sizes': [{
                'id': line.id, 'code': line.code, 'name': line.name,
                'selected': line.selected, 'is_default': line.is_system_default,
            } for line in self.size_line_ids],
            'tint': {
                'method': self.tint_numbering_method,
                'locked': self.state == 'ready',
                'shades': [{
                    'id': line.id, 'value': line.value, 'code': line.code, 'selected': line.selected,
                } for line in self.tint_shade_line_ids],
            },
            'fields': [{
                'id': line.id, 'key': line.field_key, 'label': line.label,
                'state': 'hid' if line.hidden else ('req' if line.required else 'opt'),
            } for line in self.operation_field_line_ids],
            'tax': {
                'enabled': self.operation_tax_enabled,
                'tax_id': self.operation_tax_id.id or False,
                'price_mode': self.operation_price_input_mode,
                'options': [{
                    'id': tax.id, 'name': tax.display_name, 'amount': tax.amount,
                    'amount_type': tax.amount_type, 'price_include': bool(tax.price_include),
                } for tax in self._wof_flow_taxes()],
            },
            'pricing_policy': self.operation_pricing_policy,
            'invoice': self._wof_flow_invoice_mode(),
            'discount': {
                'enabled': self.discount_enabled,
                'limit': self.discount_default_limit,
                'reason_from': self.discount_reason_required_from,
                'override': self.discount_allow_override_request,
                'scope': self.discount_scope,
            },
            'tech': {
                'multi': self.operation_allow_multiple_technicians,
                'event': self.commission_event,
            },
            'issues': self._readiness_issues(),
        }

    def wof_flow_load(self):
        self.ensure_one()
        self._ensure_can_configure()
        self._wof_flow_prepare()
        if self.state == 'draft':
            self._write_setup_transition({'state': 'in_progress'})
        return self._wof_flow_snapshot()

    # ------------------------------------------------------------------- ops
    def wof_flow_apply(self, op, payload=None):
        """Apply one change from the setup screen and return the fresh snapshot."""
        self.ensure_one()
        self._ensure_can_configure()
        handler = {
            'activity': self._wof_op_activity,
            'activity_add': self._wof_op_activity_add,
            'size': self._wof_op_size,
            'size_add': self._wof_op_size_add,
            'tint_method': self._wof_op_tint_method,
            'shade': self._wof_op_shade,
            'field': self._wof_op_field,
            'set': self._wof_op_set,
            'invoice': self._wof_op_invoice,
            'goto': self._wof_op_goto,
            'activate': self._wof_op_activate,
        }.get(op)
        if not handler:
            raise ValidationError(_('عملية غير معروفة في شاشة التهيئة.'))
        handler(payload or {})
        return self._wof_flow_snapshot()

    def _wof_line(self, lines, line_id, label):
        line = lines.filtered(lambda record: record.id == line_id)
        if not line:
            raise ValidationError(_('تعذر العثور على %s المطلوب.') % label)
        return line

    def _wof_op_activity(self, payload):
        line = self._wof_line(self.activity_line_ids, payload.get('id'), _('النشاط'))
        if 'name' in payload or 'description' in payload:
            self.env['wof.setup.activity.dialog'].create({
                'mode': 'edit', 'profile_id': self.id, 'activity_line_id': line.id,
                'name': payload.get('name', line.name),
                'description': payload.get('description', line.description or False),
            }).action_confirm()
        if 'selected' in payload:
            line.write({'selected': bool(payload['selected'])})

    def _wof_op_activity_add(self, payload):
        self.env['wof.setup.activity.dialog'].create({
            'mode': 'add', 'profile_id': self.id,
            'name': payload.get('name'), 'description': payload.get('description') or False,
        }).action_confirm()

    def _wof_op_size(self, payload):
        line = self._wof_line(self.size_line_ids, payload.get('id'), _('حجم السيارة'))
        if 'name' in payload:
            self.env['wof.setup.size.dialog'].create({
                'mode': 'edit', 'profile_id': self.id, 'size_line_id': line.id,
                'name': payload.get('name'),
            }).action_confirm()
        if 'selected' in payload:
            line.write({'selected': bool(payload['selected'])})

    def _wof_op_size_add(self, payload):
        code = (payload.get('code') or '').strip().upper()
        if not code:
            self.env['wof.setup.size.dialog'].create({
                'mode': 'add', 'profile_id': self.id, 'name': payload.get('name'),
            }).action_confirm()
            return
        name = (payload.get('name') or '').strip()
        if not name:
            raise ValidationError(_('اسم حجم السيارة مطلوب.'))
        if not TECHNICAL_CODE_RE.fullmatch(code):
            raise ValidationError(_(
                'كود الحجم يقبل الأحرف الإنجليزية الكبيرة والأرقام والشرطة والنقطة والشرطة السفلية فقط.'
            ))
        if code in self.size_line_ids.mapped('code'):
            raise ValidationError(_('كود الحجم مستخدم مسبقًا.'))
        if self.env['wof.setup.size.line'].search_count([
            ('profile_id', '=', self.id), ('name', '=ilike', name),
        ]):
            raise ValidationError(_('اسم حجم السيارة مستخدم مسبقًا في مركز التهيئة.'))
        self.env['wof.setup.size.line'].create({
            'profile_id': self.id,
            'sequence': max(self.size_line_ids.mapped('sequence') or [0]) + 10,
            'code': code, 'name': name, 'selected': True, 'is_system_default': False,
        })

    def _wof_op_tint_method(self, payload):
        self._set_tint_numbering_method(payload.get('method'))

    def _wof_op_shade(self, payload):
        line = self._wof_line(self.tint_shade_line_ids, payload.get('id'), _('درجة اللون'))
        if 'value' in payload:
            self.env['wof.setup.tint.dialog'].create({
                'profile_id': self.id, 'tint_line_id': line.id, 'name': payload.get('value'),
            }).action_confirm()
        if 'selected' in payload:
            line.write({'selected': bool(payload['selected'])})

    def _wof_op_field(self, payload):
        line = self._wof_line(self.operation_field_line_ids, payload.get('id'), _('الحقل'))
        state = payload.get('state')
        if state not in ('req', 'opt', 'hid'):
            raise ValidationError(_('حالة الحقل غير صحيحة.'))
        line.write({'required': state == 'req', 'hidden': state == 'hid'})
        if line.field_key == 'technician':
            # One decision in the UI: the field policy drives the legacy flag.
            self.write({'operation_technician_required': state == 'req'})

    def _wof_op_set(self, payload):
        vals = {}
        for name, value in payload.items():
            kind = FLOW_SCALARS.get(name)
            if not kind:
                raise ValidationError(_('لا يمكن تعديل هذا الإعداد من شاشة التهيئة.'))
            if kind == 'bool':
                vals[name] = bool(value)
            elif kind == 'percent':
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    raise ValidationError(_('أدخل نسبة صحيحة بين 0 و100.'))
                if number < 0 or number > 100:
                    raise ValidationError(_('النسبة يجب أن تكون بين 0 و100.'))
                vals[name] = number
            elif kind == 'tax':
                if value and value not in self._wof_flow_taxes().ids:
                    raise ValidationError(_('الضريبة المختارة غير متاحة لهذه الشركة.'))
                vals[name] = value or False
            else:
                if value not in kind:
                    raise ValidationError(_('قيمة غير صحيحة لهذا الإعداد.'))
                vals[name] = value
        if vals:
            self.write(vals)

    def _wof_op_invoice(self, payload):
        mode = payload.get('mode')
        if mode == 'after':
            self.write({'operation_invoice_after_full_payment': True})
        elif mode == 'auto':
            self.write({'operation_auto_invoice': True})
        elif mode == 'manual':
            self.write({'operation_auto_invoice': False, 'operation_invoice_after_full_payment': False})
        else:
            raise ValidationError(_('طريقة الفوترة غير صحيحة.'))

    def _wof_op_goto(self, payload):
        step = payload.get('step')
        if step not in FLOW_STEPS:
            raise ValidationError(_('خطوة غير معروفة.'))
        if step in ('operations', 'review'):
            self._ensure_default_operation_fields()
            self._ensure_default_operation_tax()
        if step == 'review':
            self._sync_operation_compatibility()
        vals = {'current_step': step}
        if self.state == 'draft':
            vals['state'] = 'in_progress'
        if step != self.current_step or 'state' in vals:
            self._write_setup_transition(vals)

    def _wof_op_activate(self, payload):
        self.activate_setup()
