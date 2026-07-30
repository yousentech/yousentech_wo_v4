# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class WofInstallationMaterialLine(models.Model):
    _name = 'wof.installation.material.line'
    _inherit = ['wof.api.mixin']
    _description = 'مادة مستخدمة في أمر تركيب'
    _order = 'id'
    _check_company_auto = True

    order_id = fields.Many2one(
        'wof.installation.order', string="أمر التركيب", required=True,
        ondelete='cascade', check_company=True, index=True,
    )
    order_line_id = fields.Many2one(
        'wof.installation.order.line', string="الخدمة المرتبطة",
        ondelete='restrict', check_company=True,
        domain="[('order_id', '=', order_id)]",
    )
    company_id = fields.Many2one(
        related='order_id.company_id', store=True, readonly=True, index=True,
    )
    product_id = fields.Many2one(
        'product.product', string="المادة", required=True,
        ondelete='restrict', check_company=True, index=True,
    )
    quantity = fields.Float(string="الكمية المستخدمة", required=True, default=1.0)
    uom_id = fields.Many2one(
        related='product_id.uom_id', string="وحدة القياس",
        store=True, readonly=True,
    )
    note = fields.Char(string="ملاحظة")
    recorded_by_id = fields.Many2one(
        'res.users', string="سجلها", required=True, readonly=True,
        default=lambda self: self.env.user, ondelete='restrict',
    )
    recorded_at = fields.Datetime(
        string="وقت التسجيل", required=True, readonly=True,
        default=fields.Datetime.now,
    )
    stock_move_id = fields.Many2one(
        'stock.move', string="حركة المخزون", readonly=True, copy=False,
        ondelete='restrict', check_company=True,
    )

    _sql_constraints = [
        (
            'installation_material_quantity_positive',
            'check(quantity > 0)',
            'كمية المادة المستخدمة يجب أن تكون أكبر من صفر.',
        ),
    ]

    @api.constrains('order_id', 'order_line_id')
    def _check_order_line(self):
        for material in self:
            if (
                material.order_line_id
                and material.order_line_id.order_id != material.order_id
            ):
                raise ValidationError(
                    'الخدمة المرتبطة بالمادة يجب أن تتبع أمر التركيب نفسه.'
                )

    @api.constrains('product_id')
    def _check_material_product(self):
        for material in self:
            if material.product_id.type == 'service':
                raise ValidationError(
                    'المادة المستخدمة يجب أن تكون منتجًا قابلًا للاستهلاك وليست خدمة.'
                )

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for incoming in vals_list:
            vals = dict(incoming)
            vals.pop('company_id', None)
            vals.pop('uom_id', None)
            order = self.env['wof.installation.order'].browse(
                vals.get('order_id')
            ).exists()
            self._ensure_material_editor(order)
            vals['recorded_by_id'] = self.env.user.id
            vals['recorded_at'] = fields.Datetime.now()
            vals.pop('stock_move_id', None)
            prepared.append(vals)
        return super().create(prepared)

    def write(self, vals):
        vals = dict(vals)
        if {
            'order_id',
            'company_id',
            'uom_id',
            'recorded_by_id',
            'recorded_at',
            'stock_move_id',
        }.intersection(vals):
            raise ValidationError(
                'أمر المادة وبيانات تدقيقها وحركة المخزون لا تعدل يدويًا.'
            )
        for line in self:
            self._ensure_material_editor(line.order_id)
        return super().write(vals)

    def unlink(self):
        for line in self:
            self._ensure_material_editor(line.order_id)
            if line.stock_move_id:
                raise ValidationError(
                    'لا يمكن حذف مادة مرتبطة بحركة مخزون.'
                )
        return super().unlink()

    @api.model
    def _ensure_material_editor(self, order):
        if not order:
            raise ValidationError('يجب تحديد أمر تركيب صالح للمادة.')
        if order.state != 'in_progress':
            raise ValidationError(
                'تسجيل المواد أو تعديلها متاح أثناء التنفيذ فقط.'
            )
        profile = order._profile()
        if not profile.use_inventory:
            raise ValidationError(
                'تسجيل المواد معطل في تهيئة هذا الفرع.'
            )
        if not any(
            self.env.user.has_group(group)
            for group in (
                'yousentech_wo_v4.group_wo_technician',
                'yousentech_wo_v4.group_wo_supervisor',
                'yousentech_wo_v4.group_wo_manager',
            )
        ):
            raise AccessError(
                'تسجيل المواد متاح للفني أو المشرف أو مدير المركز.'
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
                'يمكن للفني تسجيل مواد الأوامر المسندة إليه فقط.'
            )
