# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class WofCompanyProfileDiscountPolicy(models.Model):
    _inherit = 'wof.company.profile'

    discount_enabled = fields.Boolean(string='تفعيل الخصومات', default=False)
    discount_default_limit = fields.Float(string='الحد الافتراضي للخصم %', default=0.0)
    discount_allow_override_request = fields.Boolean(
        string='السماح بطلب تجاوز حد الخصم', default=True,
    )
    discount_reason_required_from = fields.Float(
        string='سبب الخصم إلزامي من %', default=0.0,
    )

    @api.constrains('discount_default_limit', 'discount_reason_required_from')
    def _check_discount_policy_ranges(self):
        for record in self:
            for value, label in (
                (record.discount_default_limit, 'الحد الافتراضي للخصم'),
                (record.discount_reason_required_from, 'نسبة إلزام سبب الخصم'),
            ):
                if value < 0 or value > 100:
                    raise ValidationError('%s يجب أن تكون بين 0 و100.' % label)


class WofFilmCategoryDiscountPolicy(models.Model):
    _inherit = 'wof.film.category'

    use_system_discount_policy = fields.Boolean(
        string='استخدام سياسة خصم النظام', default=True,
    )
    discount_enabled = fields.Boolean(string='السماح بالخصم', default=False)
    discount_limit = fields.Float(string='الحد الأقصى للخصم %', default=0.0)

    @api.constrains('discount_limit')
    def _check_discount_limit(self):
        for record in self:
            if record.discount_limit < 0 or record.discount_limit > 100:
                raise ValidationError('حد خصم الخدمة يجب أن يكون بين 0 و100.')

    def _discount_company_policy(self):
        self.ensure_one()
        return self.env['wof.company.profile'].search(
            [('company_id', '=', self.company_id.id)], limit=1,
        )

    def get_discount_policy(self, part_line=None, car_size=None):
        """Resolve company -> service -> component -> size discount policy.

        The most specific configured level wins.  This method intentionally
        does not apply user permissions; that is a later policy layer.
        """
        self.ensure_one()
        profile = self._discount_company_policy()
        enabled = bool(profile.discount_enabled)
        limit = profile.discount_default_limit if enabled else 0.0
        source = 'company'

        if not self.use_system_discount_policy:
            enabled = self.discount_enabled
            limit = self.discount_limit if enabled else 0.0
            source = 'service'

        if part_line:
            part_line.ensure_one()
            if part_line.header_id != self:
                raise ValidationError('المكوّن لا يتبع الخدمة المحددة.')
            if part_line.discount_policy != 'inherit':
                enabled = part_line.discount_policy == 'allow'
                limit = part_line.discount_limit if enabled else 0.0
                source = 'component'

            if car_size:
                size_rule = part_line.discount_size_rule_ids.filtered(
                    lambda rule: rule.car_size_id == car_size
                )[:1]
                if size_rule:
                    enabled = size_rule.discount_policy == 'allow'
                    limit = size_rule.discount_limit if enabled else 0.0
                    source = 'size'

        return {
            'enabled': bool(enabled),
            'limit': max(0.0, min(float(limit or 0.0), 100.0)),
            'source': source,
            'scope': profile.discount_scope if profile else 'order',
            'allow_override_request': bool(
                profile and profile.discount_allow_override_request
            ),
            'reason_required_from': (
                profile.discount_reason_required_from if profile else 0.0
            ),
        }


class WofFilmPartDiscountPolicy(models.Model):
    _inherit = 'wof.film.parts.lines'

    discount_policy = fields.Selection(
        [('inherit', 'يرث السياسة'), ('allow', 'يسمح بالخصم'), ('deny', 'يمنع الخصم')],
        string='سياسة الخصم', default='inherit', required=True,
    )
    discount_limit = fields.Float(string='الحد الأقصى للخصم %', default=0.0)
    discount_size_rule_ids = fields.One2many(
        'wof.film.parts.discount.rule', 'part_line_id',
        string='حدود الخصم حسب حجم السيارة',
    )

    @api.constrains('discount_limit')
    def _check_discount_limit(self):
        for record in self:
            if record.discount_limit < 0 or record.discount_limit > 100:
                raise ValidationError('حد خصم المكوّن يجب أن يكون بين 0 و100.')

    def get_discount_policy(self, car_size=None):
        self.ensure_one()
        return self.header_id.get_discount_policy(self, car_size)


class WofFilmPartDiscountRule(models.Model):
    _name = 'wof.film.parts.discount.rule'
    _description = 'سياسة خصم المكوّن حسب حجم السيارة'
    _order = 'part_line_id, car_size_id'
    _check_company_auto = True

    part_line_id = fields.Many2one(
        'wof.film.parts.lines', string='مكوّن الخدمة', required=True,
        ondelete='cascade', check_company=True, index=True,
    )
    company_id = fields.Many2one(
        related='part_line_id.company_id', store=True, readonly=True, index=True,
    )
    car_size_id = fields.Many2one(
        'wof.car.size', string='حجم السيارة', required=True,
        ondelete='restrict', check_company=True, index=True,
    )
    discount_policy = fields.Selection(
        [('allow', 'يسمح بالخصم'), ('deny', 'يمنع الخصم')],
        string='سياسة الخصم', default='allow', required=True,
    )
    discount_limit = fields.Float(string='الحد الأقصى للخصم %', default=0.0)

    _sql_constraints = [
        ('part_size_discount_unique', 'unique(part_line_id, car_size_id)',
         'توجد سياسة خصم لهذا المكوّن وحجم السيارة مسبقًا.'),
        ('discount_limit_range', 'check(discount_limit >= 0 AND discount_limit <= 100)',
         'حد الخصم يجب أن يكون بين 0 و100.'),
    ]

    @api.constrains('part_line_id', 'car_size_id')
    def _check_same_company(self):
        for record in self:
            if record.car_size_id.company_id != record.company_id:
                raise ValidationError('حجم السيارة وسياسة المكوّن يجب أن يتبعا نفس الشركة.')
