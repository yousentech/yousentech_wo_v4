# -*- coding: utf-8 -*-

import json
import re
import uuid

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


OPERATION_SOURCES = [
    ('odoo_web', 'Odoo Web'),
    ('flutter', 'Flutter'),
    ('api', 'API'),
    ('import', 'استيراد'),
]

TECHNICAL_CODE_RE = re.compile(r'^[A-Z0-9][A-Z0-9._-]*$')
OPERATION_SOURCE_TOKEN = object()


def _new_public_uuid(_recordset=None):
    """Return a UUID4 for both direct calls and Odoo field defaults."""
    return str(uuid.uuid4())


def _is_canonical_uuid4(value):
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError):
        return False
    return parsed.version == 4 and str(parsed) == value


def _trusted_operation_source(env):
    if env.context.get('wof_operation_source_token') is OPERATION_SOURCE_TOKEN:
        source = env.context.get('wof_operation_source')
        if source in dict(OPERATION_SOURCES):
            return source
    return 'odoo_web'


class WofApiMixin(models.AbstractModel):
    _name = 'wof.api.mixin'
    _description = 'أساس الكيانات القابلة للتكامل'

    public_uuid = fields.Char(
        string="المرجع العام",
        required=True,
        default=_new_public_uuid,
        readonly=True,
        copy=False,
        index=True,
    )
    operation_source = fields.Selection(
        OPERATION_SOURCES,
        string="مصدر الإنشاء",
        required=True,
        default='odoo_web',
        readonly=True,
        copy=False,
        index=True,
    )

    _sql_constraints = [
        ('public_uuid_unique', 'unique(public_uuid)', 'المرجع العام مستخدم مسبقًا.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'code' in self._fields and isinstance(vals.get('code'), str):
                vals['code'] = vals['code'].strip().upper()
                if vals['code'] and not TECHNICAL_CODE_RE.fullmatch(vals['code']):
                    raise ValidationError(
                        'الكود التقني يقبل الأحرف الإنجليزية الكبيرة والأرقام '
                        'والشرطة والنقطة والشرطة السفلية فقط.'
                    )
            vals['public_uuid'] = _new_public_uuid()
            # The identity token cannot be serialized or forged through RPC.
            vals['operation_source'] = _trusted_operation_source(self.env)
        return super().create(vals_list)

    @api.constrains('public_uuid')
    def _check_public_uuid(self):
        for record in self:
            if not _is_canonical_uuid4(record.public_uuid):
                raise ValidationError('المرجع العام يجب أن يكون UUID v4 صالحًا.')

    def write(self, vals):
        if 'code' in self._fields and isinstance(vals.get('code'), str):
            vals['code'] = vals['code'].strip().upper()
            if vals['code'] and not TECHNICAL_CODE_RE.fullmatch(vals['code']):
                raise ValidationError(
                    'الكود التقني يقبل الأحرف الإنجليزية الكبيرة والأرقام '
                    'والشرطة والنقطة والشرطة السفلية فقط.'
                )
        if 'public_uuid' in vals and any(
            record.public_uuid != vals['public_uuid'] for record in self
        ):
            raise UserError('لا يمكن تغيير المرجع العام بعد إنشاء السجل.')
        if 'operation_source' in vals and any(
            record.operation_source != vals['operation_source']
            for record in self
        ):
            raise UserError('لا يمكن تغيير مصدر إنشاء السجل.')
        return super().write(vals)

    def _audit_event(self, event_code, payload=None):
        self.ensure_one()
        company = self.company_id if 'company_id' in self._fields else self.env.company
        # Audit rows are append-only and users deliberately have no create ACL.
        # Escalation is limited to inserting a server-built row after business access checks.
        return self.env['wof.audit.log'].sudo().create({
            'event_code': event_code,
            'model_name': self._name,
            'record_public_uuid': self.public_uuid,
            'company_id': company.id,
            'user_id': self.env.user.id,
            'operation_source': _trusted_operation_source(self.env),
            'payload_json': json.dumps(payload or {}, ensure_ascii=False, default=str),
        })

    def _with_operation_source(self, source):
        """Return a trusted internal environment for a reviewed integration layer."""
        if source not in dict(OPERATION_SOURCES):
            raise ValidationError('مصدر العملية غير معروف.')
        return self.with_context(
            wof_operation_source=source,
            wof_operation_source_token=OPERATION_SOURCE_TOKEN,
        )


class ResCompany(models.Model):
    _inherit = 'res.company'

    wof_public_uuid = fields.Char(
        string="المرجع العام",
        required=True,
        default=_new_public_uuid,
        readonly=True,
        copy=False,
        index=True,
    )

    _sql_constraints = [
        ('wof_company_public_uuid_unique', 'unique(wof_public_uuid)',
         'المرجع العام للشركة مستخدم مسبقًا.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['wof_public_uuid'] = _new_public_uuid()
        return super().create(vals_list)

    @api.constrains('wof_public_uuid')
    def _check_wof_public_uuid(self):
        for record in self:
            if not _is_canonical_uuid4(record.wof_public_uuid):
                raise ValidationError('المرجع العام للشركة يجب أن يكون UUID v4 صالحًا.')

    def write(self, vals):
        if 'wof_public_uuid' in vals and any(
            record.wof_public_uuid != vals['wof_public_uuid'] for record in self
        ):
            raise UserError('لا يمكن تغيير المرجع العام للشركة.')
        return super().write(vals)


class ResUsers(models.Model):
    _inherit = 'res.users'

    wof_public_uuid = fields.Char(
        string="المرجع العام",
        required=True,
        default=_new_public_uuid,
        readonly=True,
        copy=False,
        index=True,
    )

    _sql_constraints = [
        ('wof_user_public_uuid_unique', 'unique(wof_public_uuid)',
         'المرجع العام للمستخدم مستخدم مسبقًا.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['wof_public_uuid'] = _new_public_uuid()
        return super().create(vals_list)

    @api.constrains('wof_public_uuid')
    def _check_wof_public_uuid(self):
        for record in self:
            if not _is_canonical_uuid4(record.wof_public_uuid):
                raise ValidationError('المرجع العام للمستخدم يجب أن يكون UUID v4 صالحًا.')

    def write(self, vals):
        if 'wof_public_uuid' in vals and any(
            record.wof_public_uuid != vals['wof_public_uuid'] for record in self
        ):
            raise UserError('لا يمكن تغيير المرجع العام للمستخدم.')
        return super().write(vals)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    wof_public_uuid = fields.Char(
        string="المرجع العام لنظام العناية",
        required=True,
        default=_new_public_uuid,
        readonly=True,
        copy=False,
        index=True,
    )

    _sql_constraints = [
        (
            'wof_partner_public_uuid_unique',
            'unique(wof_public_uuid)',
            'المرجع العام للعميل مستخدم مسبقًا.',
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['wof_public_uuid'] = _new_public_uuid()
        return super().create(vals_list)

    @api.constrains('wof_public_uuid')
    def _check_wof_public_uuid(self):
        for record in self:
            if not _is_canonical_uuid4(record.wof_public_uuid):
                raise ValidationError(
                    'المرجع العام للعميل يجب أن يكون UUID v4 صالحًا.'
                )

    def write(self, vals):
        if 'wof_public_uuid' in vals and any(
            record.wof_public_uuid != vals['wof_public_uuid']
            for record in self
        ):
            raise UserError(
                'لا يمكن تغيير المرجع العام للعميل بعد إنشائه.'
            )
        return super().write(vals)


class WofAuditLog(models.Model):
    _name = 'wof.audit.log'
    _description = 'سجل تدقيق نظام العناية'
    _order = 'occurred_at desc, id desc'

    public_uuid = fields.Char(
        required=True, default=_new_public_uuid,
        readonly=True, copy=False, index=True,
    )
    event_code = fields.Char(required=True, readonly=True, index=True)
    model_name = fields.Char(required=True, readonly=True, index=True)
    record_public_uuid = fields.Char(required=True, readonly=True, index=True)
    company_id = fields.Many2one(
        'res.company', required=True, readonly=True, ondelete='restrict', index=True,
    )
    user_id = fields.Many2one(
        'res.users', required=True, readonly=True, ondelete='restrict', index=True,
    )
    operation_source = fields.Selection(
        OPERATION_SOURCES, required=True, readonly=True, index=True,
    )
    occurred_at = fields.Datetime(
        required=True, default=fields.Datetime.now, readonly=True, index=True,
    )
    payload_json = fields.Text(readonly=True)

    _sql_constraints = [
        ('audit_public_uuid_unique', 'unique(public_uuid)', 'مرجع سجل التدقيق مكرر.'),
    ]

    @api.constrains('public_uuid')
    def _check_public_uuid(self):
        for record in self:
            if not _is_canonical_uuid4(record.public_uuid):
                raise ValidationError('مرجع سجل التدقيق يجب أن يكون UUID v4 صالحًا.')

    def write(self, vals):
        raise UserError('سجل التدقيق غير قابل للتعديل.')

    def unlink(self):
        raise UserError('سجل التدقيق غير قابل للحذف.')


class ProductProduct(models.Model):
    _name = 'product.product'
    _inherit = 'product.product'

    wof_public_uuid = fields.Char(
        string="مرجع نظام العناية",
        required=True,
        default=_new_public_uuid,
        readonly=True,
        copy=False,
        index=True,
    )
    wof_operation_source = fields.Selection(
        OPERATION_SOURCES,
        string="مصدر سجل نظام العناية",
        required=True,
        default='odoo_web',
        readonly=True,
        copy=False,
        index=True,
    )

    _sql_constraints = [
        ('wof_product_public_uuid_unique', 'unique(wof_public_uuid)',
         'مرجع منتج نظام العناية مستخدم مسبقًا.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['wof_public_uuid'] = _new_public_uuid()
            vals['wof_operation_source'] = _trusted_operation_source(self.env)
        return super().create(vals_list)

    def _with_operation_source(self, source):
        """Return a trusted internal environment for a reviewed integration layer."""
        if source not in dict(OPERATION_SOURCES):
            raise ValidationError('مصدر العملية غير معروف.')
        return self.with_context(
            wof_operation_source=source,
            wof_operation_source_token=OPERATION_SOURCE_TOKEN,
        )

    @api.constrains('wof_public_uuid')
    def _check_wof_public_uuid(self):
        for record in self:
            if not _is_canonical_uuid4(record.wof_public_uuid):
                raise ValidationError(
                    'مرجع منتج نظام العناية يجب أن يكون UUID v4 صالحًا.'
                )

    def write(self, vals):
        if 'wof_public_uuid' in vals and any(
            record.wof_public_uuid != vals['wof_public_uuid']
            for record in self
        ):
            raise UserError('لا يمكن تغيير مرجع منتج نظام العناية.')
        if 'wof_operation_source' in vals and any(
            record.wof_operation_source != vals['wof_operation_source']
            for record in self
        ):
            raise UserError('لا يمكن تغيير مصدر إنشاء منتج نظام العناية.')
        return super().write(vals)
