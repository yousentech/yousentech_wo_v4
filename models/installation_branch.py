# -*- coding: utf-8 -*-
"""Everything on an installation order follows its branch (company).

Films, products and the setup are shared by all branches, while taxes, stock,
journals and employees belong to a company. This module keeps the order
consistent with its branch:

* taxes: a tax from another company (not the branch or one of its parents) is
  replaced by the branch's equivalent tax (same rate and kind), or refused with a
  clear message;
* products of services, parts, extra materials and accessories: shared products
  or products of the branch (or its parents) only;
* changing the branch (before intake, nothing invoiced): prices and taxes are
  recalculated, the stock place follows, and people / technicians must belong to
  the new branch — read from the stored assignments, not through record rules.
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


def _branch_companies(company):
    """The branch and its parent companies (records they own are usable there)."""
    return company | company.parent_ids if company else company


class WofBranchHelpers(models.AbstractModel):
    _name = 'wof.branch.helpers'
    _description = 'أدوات التزام الفرع'

    @api.model
    def _wof_branch_tax(self, taxes, company):
        """Taxes usable in ``company``: kept when they belong to it (or a parent),
        else replaced by its tax with the same rate and kind. The tax's own data is
        read directly: it may belong to a company the user cannot access."""
        result = self.env['account.tax']
        allowed = _branch_companies(company)
        if not taxes:
            return result
        self.env['account.tax'].flush_model(['company_id', 'type_tax_use', 'amount_type', 'amount', 'price_include', 'name'])
        self.env.cr.execute("""
            SELECT t.id, t.company_id, t.type_tax_use, t.amount_type, t.amount, t.price_include, t.name, c.name
              FROM account_tax t LEFT JOIN res_company c ON c.id = t.company_id WHERE t.id IN %s
        """, (tuple(taxes.ids),))
        for tax_id, company_id, use, kind, amount, included, name, company_name in self.env.cr.fetchall():
            if not company_id or company_id in allowed.ids:
                result |= self.env['account.tax'].browse(tax_id)
                continue
            twin = self.env['account.tax'].search([
                ('company_id', 'in', allowed.ids), ('type_tax_use', '=', use), ('amount_type', '=', kind),
                ('amount', '=', amount), ('price_include', '=', included), ('active', '=', True),
            ], limit=1)
            if not twin:
                name = name.get(self.env.lang) or name.get('en_US') if isinstance(name, dict) else name
                raise ValidationError(_(
                    'الضريبة «%(tax)s» تابعة لشركة «%(other)s» ولا توجد ضريبة مماثلة (%(rate)s%%) في فرع «%(branch)s». '
                    'أنشئ الضريبة في الفرع أو اختر ضريبة مشتركة في تهيئة الأسعار.') % {
                    'tax': name, 'other': company_name, 'rate': amount, 'branch': company.name})
            result |= twin
        return result

    @api.model
    def _wof_check_product_branch(self, product, company, where):
        if not product or not company:
            return
        self.env['product.product'].flush_model()
        self.env.cr.execute("""
            SELECT t.company_id, c.name FROM product_product p
              JOIN product_template t ON t.id = p.product_tmpl_id
              LEFT JOIN res_company c ON c.id = t.company_id WHERE p.id = %s
        """, (product.id,))
        row = self.env.cr.fetchone()
        if row and row[0] and row[0] not in _branch_companies(company).ids:
            raise ValidationError(_('الصنف المختار تابع لشركة «%(other)s» ولا يُستخدم في فرع «%(branch)s» (%(where)s).') % {
                'other': row[1], 'branch': company.name, 'where': where})


class WofOrderLineBranch(models.Model):
    _inherit = 'wof.installation.order.line'

    def write(self, vals):
        if vals.get('tax_id') and len(self) == 1 and self.company_id:
            tax = self.env['account.tax'].browse(vals['tax_id'])
            vals = dict(vals, tax_id=self.env['wof.branch.helpers']._wof_branch_tax(tax, self.company_id).id)
        elif vals.get('tax_id') and len(self) > 1:
            result = True
            for line in self:
                result = line.write(vals) and result
            return result
        result = super().write(vals)
        if vals.get('film_product_id'):
            for line in self:
                self.env['wof.branch.helpers']._wof_check_product_branch(
                    line.film_product_id, line.company_id, _('صنف الخدمة'))
        return result

    def _wof_stock_choices(self):
        choices = super()._wof_stock_choices()
        if not choices:
            return choices
        allowed = _branch_companies(self.company_id).ids
        self.env.cr.execute("""
            SELECT p.id FROM product_product p JOIN product_template t ON t.id = p.product_tmpl_id
             WHERE p.id IN %s AND (t.company_id IS NULL OR t.company_id IN %s)
        """, (tuple(c['id'] for c in choices), tuple(allowed or [0])))
        usable = {row[0] for row in self.env.cr.fetchall()}
        return [choice for choice in choices if choice['id'] in usable]


class WofOrderLinePartBranch(models.Model):
    _inherit = 'wof.installation.order.line.part'

    @api.constrains('product_id')
    def _check_product_branch(self):
        for part in self:
            self.env['wof.branch.helpers']._wof_check_product_branch(
                part.product_id, part.line_id.company_id, _('صنف الجزء'))


class WofMaterialBranch(models.Model):
    _inherit = 'wof.installation.material.line'

    @api.constrains('product_id', 'order_id')
    def _check_product_branch(self):
        for line in self:
            self.env['wof.branch.helpers']._wof_check_product_branch(
                line.product_id, line.order_id.company_id, _('مادة إضافية'))


class WofExtraBranch(models.Model):
    _inherit = 'wof.installation.extra.line'

    @api.constrains('product_id', 'order_id')
    def _check_product_branch(self):
        for line in self:
            self.env['wof.branch.helpers']._wof_check_product_branch(
                line.product_id, line.order_id.company_id, _('ملحق'))

    @api.model
    def _wof_default_taxes(self, order, product):
        taxes = super()._wof_default_taxes(order, product)
        return self.env['wof.branch.helpers']._wof_branch_tax(taxes, order.company_id) if taxes else taxes


class WofOrderBranch(models.Model):
    _inherit = 'wof.installation.order'

    def _wof_assigned_technician_ids(self):
        """Every technician on the order's services and parts, as stored."""
        self.ensure_one()
        self.env['wof.installation.order.line'].flush_model(['technician_ids'])
        self.env['wof.installation.order.line.part'].flush_model(['technician_ids'])
        self.env.cr.execute("""
            SELECT r.employee_id FROM wof_order_line_technician_rel r
              JOIN wof_installation_order_line l ON l.id = r.line_id WHERE l.order_id = %s
            UNION
            SELECT r.employee_id FROM wof_order_line_part_technician_rel r
              JOIN wof_installation_order_line_part p ON p.id = r.part_line_id
              JOIN wof_installation_order_line l ON l.id = p.line_id WHERE l.order_id = %s
        """, (self.id, self.id))
        return {row[0] for row in self.env.cr.fetchall()}

    def write(self, vals):
        moving = self.browse()
        if 'company_id' in vals:
            moving = self.filtered(lambda order: order.company_id.id != vals['company_id'])
        result = super().write(vals)
        Team = self.env['wof.team.member']
        for order in moving:
            company = order.company_id
            # Technicians must work in the new branch.
            allowed = set(Team._wof_employees(company, 'technician').ids)
            outside = order._wof_assigned_technician_ids() - allowed
            if outside:
                names = order.line_ids._wof_employee_names(list(outside))
                raise ValidationError(_('فنيون ليسوا في فريق فرع «%s»، أزلهم من الخدمات أولًا: %s.')
                                      % (company.name, '، '.join(names.values())))
            # Supervisor and salesman of the new branch.
            people = {key: order[key].id for key in ('supervisor_id', 'salesperson_id') if order[key]}
            if people:
                order._wof_check_people(people)
            # Prices, taxes and stock place of the new branch.
            order.line_ids._refresh_pricing()
            for extra in order.extra_line_ids:
                if extra.tax_ids:
                    extra.tax_ids = self.env['wof.branch.helpers']._wof_branch_tax(extra.tax_ids, company)
            for line in order.line_ids:
                self.env['wof.branch.helpers']._wof_check_product_branch(line.film_product_id, company, _('صنف الخدمة'))
            order.line_ids.part_line_ids._check_product_branch()
            order.material_line_ids._check_product_branch()
            order.extra_line_ids._check_product_branch()
        return result
