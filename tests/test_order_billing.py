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
            'name': 'موظف فوترة التركيب', 'login': 'wof_billing_tester',
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
