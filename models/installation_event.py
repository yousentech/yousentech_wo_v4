# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from .installation_order import ORDER_EVENT_TOKEN, ORDER_STATES


class WofInstallationOrderEvent(models.Model):
    _name = 'wof.installation.order.event'
    _inherit = ['wof.api.mixin']
    _description = 'حدث أمر تركيب'
    _order = 'occurred_at desc, id desc'
    _check_company_auto = True

    order_id = fields.Many2one(
        'wof.installation.order', string="أمر التركيب", required=True,
        readonly=True, ondelete='cascade', check_company=True, index=True,
    )
    company_id = fields.Many2one(
        related='order_id.company_id', store=True, readonly=True, index=True,
    )
    event_code = fields.Char(required=True, readonly=True, index=True)
    event_label = fields.Char(string="الحدث", required=True, readonly=True)
    from_state = fields.Selection(
        ORDER_STATES, string="من حالة", readonly=True,
    )
    to_state = fields.Selection(
        ORDER_STATES, string="إلى حالة", readonly=True,
    )
    user_id = fields.Many2one(
        'res.users', string="نفذه", required=True, readonly=True,
        ondelete='restrict', index=True,
    )
    occurred_at = fields.Datetime(
        string="وقت الحدث", required=True, readonly=True,
        default=fields.Datetime.now, index=True,
    )
    note = fields.Text(string="ملاحظة", readonly=True)
    details_json = fields.Text(readonly=True, groups='base.group_no_one')

    @api.model_create_multi
    def create(self, vals_list):
        if (
            self.env.context.get('wof_order_event_token')
            is not ORDER_EVENT_TOKEN
        ):
            raise AccessError(
                'أحداث أمر التركيب ينشئها الخادم فقط.'
            )
        return super().create(vals_list)

    def write(self, vals):
        raise UserError('السجل الزمني لأمر التركيب غير قابل للتعديل.')

    def unlink(self):
        raise UserError('السجل الزمني لأمر التركيب غير قابل للحذف.')
