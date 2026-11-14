# -*- coding: utf-8 -*-
"""Payments, sale order, delivery and invoice from an installation order."""

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestOrderBilling(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        root = cls.root = cls.env
        groups = ['base.group_user', 'yousentech_wo_v4.group_wo_settings', 'yousentech_wo_v4.group_wo_manager',
                  'account.group_account_invoice', 'sales_team.group_sale_salesman_all_leads',
                  'stock.group_stock_user']
        cls.user = root['res.users'].with_context(no_reset_password=True).create({
            'name': 'موظف فوترة التركيب', 'login': 'wof_billing_tester', 'email': 'billing@example.com',
            'groups_id': [(6, 0, [root.ref(g).id for g in groups])],
        })
        env = cls.env = root(user=cls.user)
        profile = env['wof.company.profile']._wof_get_profile() or env['wof.company.profile'].get_or_create_for_company()
        profile.wof_flow_load()
        if profile.state != 'ready':
            profile.wof_flow_apply('set', {'operation_tax_enabled': False})
            profile.wof_flow_apply('activate')
        cls.profile = profile

        cls.roll = root['product.product'].create({'name': 'رول فوترة', 'type': 'product'})
        service = root['product.product'].create({'name': 'خدمة زجاج فوترة', 'type': 'service', 'invoice_policy': 'order'})
        cls.part = root['wof.car.parts'].create({
            'code': 'BIL-FRONT', 'name': 'زجاج فوترة', 'part_type': 'car_part', 'product_id': service.id,
        })
        Film = env['wof.film.category']
        cls.activity = env['wof.service.type'].search([('service_options', '=', 'tint'), ('active', '=', True)], limit=1)
        cls.film = Film.browse(Film.wof_film_create(cls.activity.id, 'فيلم الفوترة', 'film'))
        cls.film.wof_film_apply('basic', {'is_effected_in_inventory': True})
        cls.film.wof_film_apply('stock_product', {'product_id': cls.roll.id})
        cls.film.wof_film_apply('comp_add', {'part_id': cls.part.id})
        kids = root['wof.car.parts']
        for code in ('BIL-HOOD', 'BIL-BUMP'):
            kids |= root['wof.car.parts'].create({
                'code': code, 'name': 'جزء %s' % code, 'part_type': 'car_part',
                'product_id': root['product.product'].create({'name': code, 'type': 'service'}).id,
            })
        cls.area = root['wof.car.parts'].create({
            'code': 'BIL-AREA', 'name': 'منطقة الفوترة', 'part_type': 'service_area',
            'product_id': root['product.product'].create({'name': 'خدمة منطقة', 'type': 'service', 'invoice_policy': 'order'}).id,
        })
        root['wof.service.area.template'].create({
            'name': 'نموذج المنطقة', 'service_area_id': cls.area.id,
            'component_ids': [(6, 0, kids.ids)], 'is_default': True,
        })
        cls.area_kids = kids
        cls.film.wof_film_apply('comp_add', {'part_id': cls.area.id})
        cls.film.wof_film_apply('policy', {'key': 'discount', 'custom': True, 'enabled': True, 'limit': 20})
        snap = cls.film.wof_matrix_load()
        for line in snap['lines']:
            line['price'] = {'mode': 'uniform', 'general': {'amount': 500, 'readonly': False}, 'sizes': {}}
        cls.film.wof_matrix_save({'lines': snap['lines']})
        cls.film.wof_film_apply('activate')

    def make_order(self):
        partner = self.root['res.partner'].create({'name': 'عميل الفوترة', 'mobile': '0500000003'})
        size = self.env['wof.car.size'].search([], limit=1)
        order = self.env['wof.installation.order'].create({
            'partner_id': partner.id, 'vehicle_plate': 'BIL 1', 'car_size_id': size.id,
            'appointment_at': '2026-12-01',
        })
        self.env['wof.installation.order.line'].create({
            'order_id': order.id, 'service_type_id': self.activity.id,
            'film_category_id': self.film.id, 'car_part_id': self.part.id,
        })
        return order

    def pay(self, order, amount):
        wizard = self.env['wof.order.payment.wizard'].with_context(default_order_id=order.id).create({'amount': amount})
        wizard.action_confirm()

    # ------------------------------------------------------------ payments
    def test_partial_then_full_payment(self):
        order = self.make_order()
        self.assertEqual(order.amount_total, 500)
        self.assertEqual(order.payment_status, 'not_paid')
        self.pay(order, 200)
        self.assertEqual(order.payment_status, 'partial')
        self.assertEqual(order.amount_residual, 300)
        self.assertEqual(order.payment_ids.wof_order_id, order)
        self.assertEqual(order.payment_ids.state, 'posted')
        self.pay(order, 300)
        self.assertEqual(order.payment_status, 'paid')
        self.assertTrue(order._wof_is_fully_paid())

    def test_payment_cannot_exceed_remaining(self):
        order = self.make_order()
        with self.assertRaises(ValidationError):
            self.pay(order, 600)

    def test_payment_needs_billing_right(self):
        order = self.make_order()
        clerk = self.root['res.users'].with_context(no_reset_password=True).create({
            'name': 'موظف بلا فوترة', 'login': 'wof_no_billing',
            'groups_id': [(6, 0, [self.root.ref('base.group_user').id, self.root.ref('yousentech_wo_v4.group_wo_user').id])],
        })
        with self.assertRaises(UserError):
            order.with_user(clerk).action_register_payment()

    # ------------------------------------------------- sale order + invoice
    def set_invoice_mode(self, mode):
        self.profile.wof_flow_apply('invoice', {'mode': mode})

    def test_manual_invoice_via_sale_order(self):
        self.set_invoice_mode('manual')
        order = self.make_order()
        order.action_confirm_arrival()
        self.assertFalse(order.invoice_id)
        order.action_create_invoice()
        sale = order.sale_order_id
        self.assertEqual(sale.state, 'sale')
        self.assertEqual(sale.wof_order_id, order)
        service = sale.order_line.filtered(lambda line: line.product_id == self.part.product_id)
        self.assertEqual(service.price_unit, 500)
        self.assertTrue(sale.order_line.filtered(lambda line: line.display_type == 'line_note' and 'فيلم الفوترة' in line.name))
        stock = sale.order_line.filtered('wof_stock_only')
        self.assertEqual(stock.product_id, self.roll)
        self.assertEqual(stock.price_unit, 0)
        self.assertIn(self.roll, sale.picking_ids.move_ids.product_id)
        invoice = order.invoice_id
        self.assertEqual(invoice.state, 'draft')
        self.assertEqual(invoice.wof_order_id, order)
        products = invoice.invoice_line_ids.filtered(lambda line: line.display_type == 'product').product_id
        self.assertEqual(products, self.part.product_id)
        self.assertEqual(invoice.amount_untaxed, 500)
        # Creating again gives the same invoice.
        self.assertEqual(order._wof_create_invoice(), invoice)

    def _discounted_invoice(self, mode):
        self.set_invoice_mode('manual')
        self.profile.wof_flow_apply('set', {
            'invoice_discount_mode': mode, 'discount_scope': 'order',
            'discount_enabled': True, 'discount_default_limit': 20,
        })
        order = self.make_order()
        order.order_discount_percent = 10
        self.assertEqual(order.amount_untaxed, 450)
        order.action_confirm_arrival()
        order.action_create_invoice()
        line = order.invoice_id.invoice_line_ids.filtered(lambda rec: rec.display_type == 'product')
        self.assertEqual(order.invoice_id.amount_untaxed, 450)
        return line

    def test_discount_visible(self):
        line = self._discounted_invoice('visible')
        self.assertEqual(line.price_unit, 500)
        self.assertAlmostEqual(line.discount, 10)

    def test_discount_net(self):
        line = self._discounted_invoice('net')
        self.assertEqual(line.price_unit, 450)
        self.assertEqual(line.discount, 0)

    def test_invoice_at_confirmation(self):
        self.set_invoice_mode('auto')
        order = self.make_order()
        order.action_confirm_arrival()
        self.assertTrue(order.invoice_id)

    def test_invoice_after_full_payment(self):
        self.set_invoice_mode('after')
        order = self.make_order()
        order.action_confirm_arrival()
        self.assertFalse(order.invoice_id)
        with self.assertRaises(ValidationError):
            order.action_create_invoice()
        self.pay(order, 200)
        self.assertFalse(order.invoice_id)
        self.pay(order, 300)
        self.assertTrue(order.invoice_id)

    def test_by_partner_without_pay_type_acts_as_cash(self):
        self.set_invoice_mode('by_partner')
        order = self.make_order()
        expected = 'confirm' if ('pay_type' in order.partner_id._fields and order.partner_id.pay_type == 'credit') else 'paid'
        self.assertEqual(order._wof_invoice_moment(), expected)

    def test_payments_matched_when_invoice_posted(self):
        self.set_invoice_mode('manual')
        order = self.make_order()
        order.action_confirm_arrival()
        self.pay(order, 500)
        order.action_create_invoice()
        order.invoice_id.action_post()
        self.assertIn(order.invoice_id.payment_state, ('paid', 'in_payment'))

    def test_services_locked_after_sale_order(self):
        self.set_invoice_mode('manual')
        order = self.make_order()
        order.action_confirm_arrival()
        order.action_create_sale_order()
        with self.assertRaises(ValidationError):
            order.line_ids.write({'quantity': 2})

    def test_commission_follows_invoice_posting(self):
        self.set_invoice_mode('manual')
        self.root['wof.film.category'].browse(self.film.id).write({'commission_event': 'invoice'})
        order = self.make_order()
        order.action_confirm_arrival()
        order.action_create_invoice()
        self.assertEqual(order.line_ids.commission_state, 'pending')
        order.invoice_id.action_post()
        self.assertEqual(order.line_ids.commission_state, 'approved')
        order.invoice_id.button_draft()
        self.assertEqual(order.line_ids.commission_state, 'pending')

    def test_accountant_can_post_the_invoice(self):
        self.set_invoice_mode('manual')
        order = self.make_order()
        order.action_confirm_arrival()
        order.action_create_invoice()
        accountant = self.root['res.users'].with_context(no_reset_password=True).create({
            'name': 'محاسب', 'login': 'wof_accountant', 'email': 'acc@example.com',
            'groups_id': [(6, 0, [self.root.ref('base.group_user').id, self.root.ref('account.group_account_invoice').id])],
        })
        order.invoice_id.with_user(accountant).action_post()
        self.assertEqual(order.invoice_id.state, 'posted')

    def test_cancel_blocked_with_posted_invoice(self):
        self.set_invoice_mode('manual')
        order = self.make_order()
        order.action_confirm_arrival()
        order.action_create_invoice()
        order.invoice_id.action_post()
        order.cancellation_reason = 'تجربة'
        with self.assertRaises(ValidationError):
            order.action_cancel()

    # ------------------------------------------------- add-service picker
    def test_catalog_and_add_services(self):
        partner = self.root['res.partner'].create({'name': 'عميل الكتالوج', 'mobile': '0500000009'})
        size = self.env['wof.car.size'].search([], limit=1)
        order = self.env['wof.installation.order'].create({
            'partner_id': partner.id, 'vehicle_plate': 'CAT 1', 'car_size_id': size.id,
        })
        catalog = order.wof_service_catalog()
        films = [film for act in catalog['activities'] for film in act['films']]
        film = next(film for film in films if film['id'] == self.film.id)
        comp = next(comp for comp in film['comps'] if comp['id'] == self.part.id)
        self.assertEqual(comp['price'], 500)
        self.assertFalse(comp['added'])
        order.wof_add_services([{'film_id': self.film.id, 'part_id': self.part.id}])
        self.assertEqual(len(order.line_ids), 1)
        self.assertEqual(order.line_ids.unit_price, 500)
        self.assertEqual(order.line_ids.film_product_id, self.roll)
        catalog = order.wof_service_catalog()
        film = next(film for act in catalog['activities'] for film in act['films'] if film['id'] == self.film.id)
        self.assertTrue(next(comp for comp in film['comps'] if comp['id'] == self.part.id)['added'])

    # ------------------------------------------------- finance and returns
    def _refund_flow_order(self):
        self.set_invoice_mode('manual')
        order = self.make_order()
        order.action_confirm_arrival()
        self.pay(order, 200)
        self.assertEqual(order.finance_state, 'due')
        self.assertEqual(order.finance_received, 200)
        self.assertEqual(order.finance_due, 300)
        self.assertEqual(order.finance_to_refund, 0)
        self.pay(order, 300)
        order.action_create_invoice()
        order.invoice_id.action_post()
        order.invalidate_recordset()
        self.assertEqual(order.finance_invoiced, 500)
        self.assertEqual(order.finance_state, 'settled')
        return order

    def credit_whole_invoice(self, order):
        action = order.action_wof_credit_note()
        wizard = self.env['account.move.reversal'].with_context(action['context']).create({
            'reason': 'مرتجع', 'journal_id': order.invoice_id.journal_id.id,
        })
        wizard.reverse_moves()
        refund = order._wof_finance_moves().filtered(lambda move: move.move_type == 'out_refund')
        self.assertEqual(refund.wof_order_id, order)
        if refund.state == 'draft':
            refund.action_post()
        order.invalidate_recordset()
        return refund

    def test_credit_note_then_refund_payment(self):
        order = self._refund_flow_order()
        self.credit_whole_invoice(order)
        self.assertEqual(order.finance_credited, 500)
        self.assertEqual(order.finance_state, 'refund')
        self.assertEqual(order.finance_to_refund, 500)
        with self.assertRaises(ValidationError):
            self.env['wof.order.payment.wizard'].with_context(
                default_order_id=order.id, default_payment_type='outbound').create({'amount': 600}).action_confirm()
        wizard = self.env['wof.order.payment.wizard'].with_context(
            default_order_id=order.id, default_payment_type='outbound').create({})
        self.assertEqual(wizard.amount, 500)
        wizard.action_confirm()
        order.invalidate_recordset()
        self.assertEqual(order.finance_refunded, 500)
        self.assertEqual(order.finance_state, 'settled')
        self.assertEqual(order.finance_to_refund, 0)

    def test_cancel_after_full_return(self):
        order = self._refund_flow_order()
        order.cancellation_reason = 'مرتجع كامل'
        with self.assertRaises(ValidationError):
            order.action_cancel()  # invoice not credited yet
        self.credit_whole_invoice(order)
        with self.assertRaises(ValidationError):
            order.action_cancel()  # money not paid back yet
        self.env['wof.order.payment.wizard'].with_context(
            default_order_id=order.id, default_payment_type='outbound').create({}).action_confirm()
        # Stock went out with the sale order: return it before cancelling.
        delivered = order.sale_order_id.picking_ids.filtered(lambda pick: pick.state == 'done')
        if delivered:
            with self.assertRaises(ValidationError):
                order.action_cancel()
            return
        order.action_cancel()
        self.assertEqual(order.state, 'cancelled')
        self.assertEqual(order.sale_order_id.state, 'cancel')

    # ------------------------------------------------- service-area parts
    def test_service_area_parts(self):
        self.set_invoice_mode('manual')
        partner = self.root['res.partner'].create({'name': 'عميل المنطقة', 'mobile': '0500000044'})
        size = self.env['wof.car.size'].search([], limit=1)
        order = self.env['wof.installation.order'].create({
            'partner_id': partner.id, 'vehicle_plate': 'BIL 9', 'car_size_id': size.id,
        })
        order.wof_add_services([{'film_id': self.film.id, 'part_id': self.area.id}])
        line = order.line_ids
        self.assertEqual(line.part_line_ids.part_id, self.area_kids)
        self.assertEqual(line.part_line_ids.product_id, self.roll)
        data = line.wof_area_load()
        self.assertEqual(len(data['parts']), 2)
        # Quantity per part; the stock line sums the parts.
        line.wof_area_update(line.part_line_ids.ids, {'product_qty': 1.5})
        self.assertEqual(line._wof_stock_needs(), [(self.roll, 1.5), (self.roll, 1.5)])
        # One part without product -> counted as missing.
        line.wof_area_update(line.part_line_ids[:1].ids, {'product_id': False})
        self.assertEqual(line.part_missing_product, 1)
        line.wof_area_update(line.part_line_ids[:1].ids, {'product_id': self.roll.id})
        order.action_confirm_arrival()
        order.action_create_sale_order()
        stock = order.sale_order_id.order_line.filtered('wof_stock_only')
        self.assertEqual(stock.product_uom_qty, 3.0)
        note = order.sale_order_id.order_line.filtered(lambda rec: rec.display_type == 'line_note')
        self.assertIn('جزء BIL-HOOD', note.name)

    def test_row_discount_can_be_cleared(self):
        self.profile.wof_flow_apply('set', {'discount_scope': 'service', 'discount_enabled': True,
                                            'discount_default_limit': 20})
        order = self.make_order()
        line = order.line_ids
        line.wof_line_update({'discount_type': 'percent', 'discount_value': 10})
        self.assertEqual(line.discount_amount, 50)
        data = line.wof_line_update({'discount_value': ''})
        self.assertEqual(line.discount_value, 0)
        self.assertEqual(line.discount_amount, 0)
        self.assertTrue(data['discount']['shown'])
