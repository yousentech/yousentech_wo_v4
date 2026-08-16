# -*- coding: utf-8 -*-

import hashlib
import json

from psycopg2 import IntegrityError

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


ORDER_TRANSITION_TOKEN = object()
ORDER_LINE_INTERNAL_TOKEN = object()
ORDER_EVENT_TOKEN = object()
IDEMPOTENCY_TOKEN = object()
ORDER_PARENT_CREATE_TOKEN = object()

ORDER_STATES = [
    ('draft', 'مسودة'),
    ('scheduled', 'موعد / وصول مؤكد'),
    ('intake', 'تم الاستلام والفحص'),
    ('in_progress', 'قيد التنفيذ'),
    ('quality', 'فحص الجودة'),
    ('ready', 'جاهز للتسليم'),
    ('delivered', 'تم التسليم'),
    ('cancelled', 'ملغي'),
]

STATE_PROGRESS = {
    'draft': 5,
    'scheduled': 20,
    'intake': 35,
    'in_progress': 60,
    'quality': 78,
    'ready': 92,
    'delivered': 100,
    'cancelled': 0,
}

NEXT_ACTION_LABELS = {
    'draft': 'تأكيد الموعد أو الوصول',
    'scheduled': 'إكمال الاستلام والفحص',
    'intake': 'بدء التنفيذ',
    'in_progress': 'إرسال إلى فحص الجودة',
    'quality': 'اعتماد الجودة',
    'ready': 'تسليم السيارة',
    'delivered': 'مكتمل',
    'cancelled': 'ملغي',
}

EVENT_LABELS = {
    'order.created': 'إنشاء أمر التركيب',
    'order.arrival_confirmed': 'تأكيد الموعد أو وصول السيارة',
    'order.intake_completed': 'إكمال استلام وفحص السيارة',
    'order.execution_started': 'بدء التنفيذ',
    'order.sent_to_quality': 'إرسال الأمر إلى فحص الجودة',
    'order.quality_rejected': 'إعادة الأمر إلى التنفيذ',
    'order.quality_passed': 'اعتماد فحص الجودة',
    'order.delivered': 'تسليم السيارة وإغلاق الأمر',
    'order.cancelled': 'إلغاء أمر التركيب',
    'order.price_overridden': 'تجاوز السعر المهيأ',
}

ORDER_ATTACHMENT_MIMETYPES = {
    'image/jpeg',
    'image/png',
    'image/webp',
    'image/heic',
    'image/heif',
    'application/pdf',
}
ORDER_ATTACHMENT_MAX_BYTES = 15 * 1024 * 1024


def _fingerprint_values(values):
    ignored = {
        'state',
        'public_uuid',
        'operation_source',
        'created_by_id',
        'idempotency_fingerprint',
        'name',
    }
    payload = {
        key: value
        for key, value in values.items()
        if key not in ignored
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
        default=str,
    )
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


class WofInstallationOrder(models.Model):
    _name = 'wof.installation.order'
    _inherit = [
        'wof.api.mixin',
        'mail.thread',
        'mail.activity.mixin',
    ]
    _description = 'أمر تركيب العناية بالسيارة'
    _order = 'appointment_at desc, id desc'
    _check_company_auto = True

    name = fields.Char(
        string="رقم الأمر", required=True, default='جديد',
        readonly=True, copy=False, index=True, tracking=True,
    )
    active = fields.Boolean(default=True, tracking=True)
    state = fields.Selection(
        ORDER_STATES, string="الحالة", required=True,
        default='draft', readonly=True, copy=False, index=True, tracking=True,
    )
    stage_progress = fields.Integer(
        string="تقدم المرحلة", compute='_compute_stage_ui',
    )
    next_action_label = fields.Char(
        string="الإجراء التالي", compute='_compute_stage_ui',
    )
    company_id = fields.Many2one(
        'res.company', string="الفرع / الشركة", required=True,
        default=lambda self: self.env.company, ondelete='restrict',
        index=True, tracking=True,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id', store=True, readonly=True,
    )
    created_by_id = fields.Many2one(
        'res.users', string="أنشأه", required=True, readonly=True,
        default=lambda self: self.env.user, ondelete='restrict', index=True,
    )
    idempotency_key = fields.Char(
        string="مفتاح منع التكرار", readonly=True, copy=False, index=True,
    )
    idempotency_fingerprint = fields.Char(
        readonly=True, copy=False, groups='base.group_no_one',
    )

    partner_id = fields.Many2one(
        'res.partner', string="العميل", required=True,
        ondelete='restrict', check_company=True, index=True, tracking=True,
    )
    partner_mobile = fields.Char(
        string="جوال العميل", related='partner_id.mobile', readonly=True,
    )
    partner_phone = fields.Char(
        string="هاتف العميل", related='partner_id.phone', readonly=True,
    )
    customer_notes = fields.Text(string="ملاحظات العميل")

    vehicle_plate = fields.Char(
        string="رقم اللوحة", required=True, index=True, tracking=True,
    )
    vehicle_vin = fields.Char(string="رقم الهيكل", index=True)
    vehicle_manufacturer_id = fields.Many2one(
        'wof.car.manufactory', string="الماركة", ondelete='restrict',
    )
    vehicle_model_id = fields.Many2one(
        'wof.car.type', string="الموديل", ondelete='restrict',
        domain="[('manufactory_id', '=', vehicle_manufacturer_id)]",
    )
    vehicle_year_id = fields.Many2one(
        'wof.car.manufactory.year', string="السنة", ondelete='restrict',
    )
    vehicle_color = fields.Char(string="اللون")
    car_size_id = fields.Many2one(
        'wof.car.size', string="حجم السيارة", required=True,
        ondelete='restrict', check_company=True, index=True,
    )
    odometer = fields.Integer(string="قراءة العداد", copy=False)

    appointment_at = fields.Datetime(
        string="الموعد", copy=False, index=True, tracking=True,
    )
    expected_delivery_at = fields.Datetime(
        string="موعد التسليم المتوقع", copy=False, index=True, tracking=True,
    )
    use_appointments = fields.Boolean(
        string="المواعيد مفعلة", required=True, readonly=True,
    )
    advisor_id = fields.Many2one(
        'res.users', string="مستشار الخدمة", required=True,
        default=lambda self: self.env.user, ondelete='restrict',
        index=True,
    )
    supervisor_id = fields.Many2one(
        'res.users', string="مشرف التشغيل", ondelete='restrict',
        index=True,
    )
    technician_ids = fields.Many2many(
        'res.users',
        'wof_installation_order_technician_rel',
        'order_id',
        'user_id',
        string="الفنيون",
    )
    advisor_candidate_ids = fields.Many2many(
        'res.users', compute='_compute_assignment_candidates',
    )
    supervisor_candidate_ids = fields.Many2many(
        'res.users', compute='_compute_assignment_candidates',
    )
    technician_candidate_ids = fields.Many2many(
        'res.users', compute='_compute_assignment_candidates',
    )

    line_ids = fields.One2many(
        'wof.installation.order.line', 'order_id',
        string="الخدمات والأجزاء", copy=True,
    )
    material_line_ids = fields.One2many(
        'wof.installation.material.line', 'order_id',
        string="المواد المستخدمة", copy=False,
    )
    event_ids = fields.One2many(
        'wof.installation.order.event', 'order_id',
        string="السجل الزمني", readonly=True, copy=False,
    )

    amount_untaxed = fields.Monetary(
        string="قبل الضريبة", currency_field='currency_id',
        compute='_compute_amounts', store=True,
    )
    amount_discount = fields.Monetary(
        string="الخصم", currency_field='currency_id',
        compute='_compute_amounts', store=True,
    )
    amount_tax = fields.Monetary(
        string="الضريبة", currency_field='currency_id',
        compute='_compute_amounts', store=True,
    )
    amount_total = fields.Monetary(
        string="الإجمالي", currency_field='currency_id',
        compute='_compute_amounts', store=True, tracking=True,
    )
    discount_scope = fields.Selection(
        [('order', 'على إجمالي الأمر'), ('service', 'على كل خدمة')],
        string="موضع الخصم", required=True, readonly=True,
    )
    order_discount_percent = fields.Float(
        string="خصم إجمالي الأمر %", default=0.0,
    )
    execution_progress = fields.Integer(
        string="تقدم التنفيذ", compute='_compute_execution_progress', store=True,
    )

    intake_condition = fields.Selection(
        [
            ('good', 'حالة جيدة'),
            ('existing_damage', 'توجد أضرار سابقة'),
            ('needs_review', 'تحتاج مراجعة إضافية'),
        ],
        string="حالة السيارة عند الاستلام",
        copy=False,
    )
    intake_notes = fields.Text(string="ملاحظات فحص الاستلام", copy=False)
    customer_approved = fields.Boolean(
        string="موافقة العميل على الأعمال والتسليم", copy=False,
    )
    customer_approval_at = fields.Datetime(readonly=True, copy=False)
    customer_approval_reference = fields.Char(
        string="مرجع الموافقة", copy=False,
    )
    before_attachment_ids = fields.Many2many(
        'ir.attachment',
        'wof_installation_before_attachment_rel',
        'order_id',
        'attachment_id',
        string="صور ومرفقات قبل التنفيذ",
        copy=False,
    )
    after_attachment_ids = fields.Many2many(
        'ir.attachment',
        'wof_installation_after_attachment_rel',
        'order_id',
        'attachment_id',
        string="صور ومرفقات بعد التنفيذ",
        copy=False,
    )

    execution_notes = fields.Text(string="ملاحظات التنفيذ")
    quality_passed = fields.Boolean(
        string="اجتاز فحص الجودة", copy=False,
    )
    quality_notes = fields.Text(string="ملاحظات الجودة", copy=False)
    delivery_notes = fields.Text(string="ملاحظات التسليم", copy=False)
    cancellation_reason = fields.Text(string="سبب الإلغاء", copy=False)

    arrival_confirmed_at = fields.Datetime(readonly=True, copy=False)
    intake_completed_at = fields.Datetime(readonly=True, copy=False)
    execution_started_at = fields.Datetime(readonly=True, copy=False)
    execution_completed_at = fields.Datetime(readonly=True, copy=False)
    quality_checked_at = fields.Datetime(readonly=True, copy=False)
    quality_checked_by_id = fields.Many2one(
        'res.users', readonly=True, copy=False, ondelete='restrict',
    )
    delivered_at = fields.Datetime(readonly=True, copy=False)
    delivered_by_id = fields.Many2one(
        'res.users', readonly=True, copy=False, ondelete='restrict',
    )
    cancelled_at = fields.Datetime(readonly=True, copy=False)
    cancelled_by_id = fields.Many2one(
        'res.users', readonly=True, copy=False, ondelete='restrict',
    )

    sale_order_id = fields.Many2one(
        'sale.order', string="أمر البيع", readonly=True, copy=False,
        ondelete='restrict', check_company=True,
    )
    invoice_id = fields.Many2one(
        'account.move', string="الفاتورة", readonly=True, copy=False,
        ondelete='restrict', check_company=True,
        domain="[('move_type', 'in', ('out_invoice', 'out_refund'))]",
    )
    warranty_status = fields.Selection(
        [
            ('not_applicable', 'غير مطبق'),
            ('pending', 'بانتظار الإصدار'),
            ('issued', 'تم الإصدار'),
        ],
        string="حالة الضمان", default='pending', required=True, copy=False,
    )
    warranty_reference = fields.Char(string="مرجع الضمان", copy=False)

    _sql_constraints = [
        (
            'installation_order_name_company_unique',
            'unique(name, company_id)',
            'رقم أمر التركيب مستخدم مسبقًا في هذا الفرع.',
        ),
        (
            'installation_order_idempotency_unique',
            'unique(company_id, idempotency_key)',
            'مفتاح منع التكرار مستخدم مسبقًا في هذا الفرع.',
        ),
        (
            'installation_order_odometer_nonnegative',
            'check(odometer >= 0)',
            'قراءة العداد لا يمكن أن تكون سالبة.',
        ),
        (
            'installation_order_discount_range',
            'check(order_discount_percent >= 0 AND order_discount_percent <= 100)',
            'خصم إجمالي الأمر يجب أن يكون بين 0 و100٪.',
        ),
    ]

    @api.depends('state')
    def _compute_stage_ui(self):
        for order in self:
            order.stage_progress = STATE_PROGRESS[order.state]
            order.next_action_label = NEXT_ACTION_LABELS[order.state]

    @api.depends(
        'line_ids.amount_untaxed',
        'line_ids.discount_amount',
        'line_ids.amount_tax',
        'line_ids.amount_total',
    )
    def _compute_amounts(self):
        for order in self:
            order.amount_untaxed = sum(order.line_ids.mapped('amount_untaxed'))
            order.amount_discount = sum(order.line_ids.mapped('discount_amount'))
            order.amount_tax = sum(order.line_ids.mapped('amount_tax'))
            order.amount_total = sum(order.line_ids.mapped('amount_total'))

    @api.depends('line_ids.execution_progress')
    def _compute_execution_progress(self):
        for order in self:
            order.execution_progress = (
                round(sum(order.line_ids.mapped('execution_progress')) / len(order.line_ids))
                if order.line_ids
                else 0
            )

    @api.depends('company_id')
    def _compute_assignment_candidates(self):
        reception_group = self.env.ref(
            'yousentech_wo_v4.group_wo_user'
        )
        supervisor_group = self.env.ref(
            'yousentech_wo_v4.group_wo_supervisor'
        )
        technician_group = self.env.ref(
            'yousentech_wo_v4.group_wo_technician'
        )
        for order in self:
            company_domain = [
                ('active', '=', True),
                ('company_ids', 'in', order.company_id.id),
            ] if order.company_id else [('id', '=', False)]
            order.advisor_candidate_ids = self.env['res.users'].search(
                company_domain + [
                    ('groups_id', 'in', (reception_group | supervisor_group).ids),
                ]
            )
            order.supervisor_candidate_ids = self.env['res.users'].search(
                company_domain + [
                    ('groups_id', 'in', supervisor_group.ids),
                ]
            )
            order.technician_candidate_ids = self.env['res.users'].search(
                company_domain + [
                    ('groups_id', 'in', technician_group.ids),
                ]
            )

    @api.constrains('vehicle_manufacturer_id', 'vehicle_model_id')
    def _check_vehicle_model(self):
        for order in self:
            if (
                order.vehicle_model_id
                and order.vehicle_manufacturer_id
                and order.vehicle_model_id.manufactory_id
                != order.vehicle_manufacturer_id
            ):
                raise ValidationError(
                    'موديل السيارة لا يتبع الماركة المحددة.'
                )

    @api.constrains(
        'company_id',
        'advisor_id',
        'supervisor_id',
        'technician_ids',
    )
    def _check_assigned_users_company(self):
        for order in self:
            users = (
                order.advisor_id
                | order.supervisor_id
                | order.technician_ids
            )
            invalid = users.filtered(
                lambda user: order.company_id not in user.company_ids
            )
            if invalid:
                raise ValidationError(
                    'المستخدمون التاليون غير مسموح لهم بالعمل في هذا الفرع: %s.'
                    % '، '.join(invalid.mapped('display_name'))
                )
            if (
                order.advisor_id
                and order.advisor_id not in order.advisor_candidate_ids
            ):
                raise ValidationError(
                    'مستشار الخدمة يجب أن يحمل دور الاستقبال أو الإشراف في هذا الفرع.'
                )
            if (
                order.supervisor_id
                and order.supervisor_id not in order.supervisor_candidate_ids
            ):
                raise ValidationError(
                    'مشرف التشغيل يجب أن يحمل دور مشرف التشغيل في هذا الفرع.'
                )
            invalid_technicians = (
                order.technician_ids - order.technician_candidate_ids
            )
            if invalid_technicians:
                raise ValidationError(
                    'المستخدمون التاليون لا يحملون دور الفني في هذا الفرع: %s.'
                    % '، '.join(invalid_technicians.mapped('display_name'))
                )
            line_technicians = order.line_ids.mapped('execution_technician_id')
            removed_assignees = line_technicians - order.technician_ids
            if removed_assignees:
                raise ValidationError(
                    'لا يمكن إزالة فني مسند إلى خدمة. أعد إسناد الخدمات أولًا: %s.'
                    % '، '.join(removed_assignees.mapped('display_name'))
                )

    @api.constrains('appointment_at', 'expected_delivery_at')
    def _check_delivery_schedule(self):
        for order in self:
            if (
                order.appointment_at
                and order.expected_delivery_at
                and order.expected_delivery_at < order.appointment_at
            ):
                raise ValidationError(
                    'موعد التسليم المتوقع يجب أن يكون بعد موعد الاستلام.'
                )

    @api.constrains('before_attachment_ids', 'after_attachment_ids', 'company_id')
    def _check_order_attachments(self):
        for order in self:
            attachments = (
                order.before_attachment_ids | order.after_attachment_ids
            )
            wrong_company = attachments.filtered(
                lambda attachment: (
                    attachment.company_id
                    and attachment.company_id != order.company_id
                )
            )
            if wrong_company:
                raise ValidationError(
                    'لا يمكن ربط مرفق تابع لفرع آخر بأمر التركيب.'
                )
            foreign_bound = attachments.filtered(
                lambda attachment: (
                    attachment.res_model
                    and (
                        attachment.res_model != order._name
                        or attachment.res_id not in {0, order.id}
                    )
                )
            )
            if foreign_bound:
                raise ValidationError(
                    'لا يمكن إعادة استخدام مرفق مرتبط بسجل آخر داخل أمر التركيب.'
                )
            invalid_type = attachments.filtered(
                lambda attachment: (
                    attachment.mimetype
                    and attachment.mimetype not in ORDER_ATTACHMENT_MIMETYPES
                )
            )
            if invalid_type:
                raise ValidationError(
                    'مرفقات أمر التركيب تقبل صور JPEG/PNG/WebP/HEIC أو PDF فقط.'
                )
            oversized = attachments.filtered(
                lambda attachment: (
                    attachment.file_size
                    and attachment.file_size > ORDER_ATTACHMENT_MAX_BYTES
                )
            )
            if oversized:
                raise ValidationError(
                    'حجم المرفق الواحد لا يمكن أن يتجاوز 15 ميجابايت.'
                )

    @api.constrains('discount_scope', 'order_discount_percent', 'line_ids')
    def _check_order_discount_policy(self):
        for order in self:
            if (
                order.discount_scope == 'service'
                and order.order_discount_percent
            ):
                raise ValidationError(
                    'تهيئة الفرع تطبق الخصم على كل خدمة؛ استخدم خصم خطوط الخدمات.'
                )
            if order.discount_scope == 'order' and order.order_discount_percent:
                exceeded = order.line_ids.filtered(
                    lambda line: (
                        line.unit_price * line.quantity > 0
                        and order.order_discount_percent
                        > line.max_discount_percent
                    )
                )
                if exceeded:
                    raise ValidationError(
                        'خصم إجمالي الأمر يتجاوز حد إحدى الخدمات: %s.'
                        % '، '.join(exceeded.mapped('car_part_id.display_name'))
                    )

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for incoming in vals_list:
            vals = dict(incoming)
            for server_owned in (
                'active',
                'arrival_confirmed_at',
                'intake_completed_at',
                'execution_started_at',
                'execution_completed_at',
                'quality_passed',
                'quality_notes',
                'quality_checked_at',
                'quality_checked_by_id',
                'customer_approved',
                'customer_approval_at',
                'customer_approval_reference',
                'delivery_notes',
                'delivered_at',
                'delivered_by_id',
                'cancelled_at',
                'cancelled_by_id',
                'cancellation_reason',
                'sale_order_id',
                'invoice_id',
                'warranty_status',
                'warranty_reference',
                'execution_notes',
                'after_attachment_ids',
            ):
                vals.pop(server_owned, None)
            company = self.env['res.company'].browse(
                vals.get('company_id') or self.env.company.id
            ).exists()
            if not company or company not in self.env.companies:
                raise AccessError(
                    _('لا يمكنك إنشاء أمر تركيب لفرع غير مسموح لك بالعمل عليه.')
                )
            profile = self._ensure_company_is_ready(company)
            vals.update({
                'active': True,
                'company_id': company.id,
                'name': self.env['ir.sequence'].with_company(company).next_by_code(
                    'wof.installation.order'
                ) or _('جديد'),
                'state': 'draft',
                'created_by_id': self.env.user.id,
                'discount_scope': profile.discount_scope,
                'use_appointments': profile.use_appointments,
                'quality_passed': False,
                'customer_approved': False,
                'warranty_status': 'pending',
            })
            vals['vehicle_plate'] = (vals.get('vehicle_plate') or '').strip().upper()
            if vals.get('vehicle_vin'):
                vals['vehicle_vin'] = vals['vehicle_vin'].strip().upper()
            if vals.get('idempotency_key'):
                vals['idempotency_key'] = vals['idempotency_key'].strip()
                vals['idempotency_fingerprint'] = (
                    vals.get('idempotency_fingerprint')
                    if self.env.context.get('wof_idempotency_token') is IDEMPOTENCY_TOKEN
                    else _fingerprint_values(vals)
                )
            else:
                vals['idempotency_key'] = False
                vals['idempotency_fingerprint'] = False
            prepared.append(vals)
        orders = super(
            WofInstallationOrder,
            self.with_context(
                wof_order_parent_create_token=ORDER_PARENT_CREATE_TOKEN
            ),
        ).create(prepared)
        for order in orders:
            order._log_business_event('order.created')
            for line in order.line_ids.filtered('use_manual_price'):
                order._log_business_event(
                    'order.price_overridden',
                    note=line.price_override_reason,
                    details={
                        'line_uuid': line.public_uuid,
                        'activity_code': line.service_type_id.code,
                        'service_code': line.film_category_id.code,
                        'part_code': line.car_part_id.code,
                        'old_price': line.configured_unit_price,
                        'new_price': line.unit_price,
                        'currency': line.currency_id.name,
                    },
                )
        return orders

    @api.model
    def create_idempotent(self, values, idempotency_key):
        """Create once for a reviewed API/controller layer and return the record."""
        if not isinstance(values, dict):
            raise ValidationError('بيانات إنشاء أمر التركيب يجب أن تكون كائنًا منظمًا.')
        key = (idempotency_key or '').strip()
        if len(key) < 16 or len(key) > 128:
            raise ValidationError(
                'مفتاح منع التكرار يجب أن يتكون من 16 إلى 128 حرفًا.'
            )
        company = self.env['res.company'].browse(
            values.get('company_id') or self.env.company.id
        ).exists()
        if not company or company not in self.env.companies:
            raise AccessError('الفرع المطلوب ليس ضمن الفروع المسموحة للمستخدم.')
        prepared = dict(values, company_id=company.id, idempotency_key=key)
        fingerprint = _fingerprint_values(prepared)
        existing = self.search([
            ('company_id', '=', company.id),
            ('idempotency_key', '=', key),
        ], limit=1)
        if existing:
            if existing.idempotency_fingerprint != fingerprint:
                raise ValidationError(
                    'IDEMPOTENCY_CONFLICT: استُخدم المفتاح نفسه بطلب مختلف.'
                )
            return existing
        prepared['idempotency_fingerprint'] = fingerprint
        try:
            with self.env.cr.savepoint():
                return self.with_context(
                    wof_idempotency_token=IDEMPOTENCY_TOKEN
                ).create(prepared)
        except IntegrityError:
            existing = self.search([
                ('company_id', '=', company.id),
                ('idempotency_key', '=', key),
            ], limit=1)
            if existing and existing.idempotency_fingerprint == fingerprint:
                return existing
            raise ValidationError(
                'IDEMPOTENCY_CONFLICT: تعذر تأكيد الطلب المكرر بأمان.'
            )

    @api.model
    def _ensure_company_is_ready(self, company):
        profile = self.env['wof.company.profile'].search([
            ('company_id', '=', company.id),
        ], limit=1)
        if not profile or profile.state != 'ready':
            raise ValidationError(
                'تهيئة نظام العناية لهذا الفرع غير مكتملة. '
                'أكمل التهيئة الأولى قبل إنشاء أمر تركيب.'
            )
        return profile
