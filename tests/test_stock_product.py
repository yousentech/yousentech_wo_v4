# -*- coding: utf-8 -*-
"""Default stock product of a film (and per tint grade) and its use on order lines."""

from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestStockProduct(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        root = cls.root = cls.env
        groups = ['base.group_user', 'yousentech_wo_v4.group_wo_settings',
                  'yousentech_wo_v4.group_wo_manager', 'stock.group_stock_user']
        user = root['res.users'].with_context(no_reset_password=True).create({
            'name': 'مدير المخزون للأفلام', 'login': 'wof_stock_product_tester',
            'groups_id': [(6, 0, [root.ref(g).id for g in groups])],
        })
        env = cls.env = root(user=user)
        profile = env['wof.company.profile']._wof_get_profile() or env['wof.company.profile'].get_or_create_for_company()
        profile.wof_flow_load()
        if profile.state != 'ready':
            profile.wof_flow_apply('set', {'operation_tax_enabled': False})
            profile.wof_flow_apply('activate')
        cls.profile = profile

        cls.roll = root['product.product'].create({'name': 'رول فيلم افتراضي', 'type': 'product'})
        cls.roll_dark = root['product.product'].create({'name': 'رول فيلم داكن', 'type': 'product'})
        service = root['product.product'].create({'name': 'زجاج مخزون', 'type': 'service'})
        cls.part = root['wof.car.parts'].create({
            'code': 'STK-FRONT', 'name': 'زجاج أمامي مخزون', 'part_type': 'car_part', 'product_id': service.id,
        })
        Film = env['wof.film.category']
        cls.activity = env['wof.service.type'].search([('service_options', '=', 'tint'), ('active', '=', True)], limit=1)
        cls.film = Film.browse(Film.wof_film_create(cls.activity.id, 'فيلم بمخزون', 'film'))
        cls.film.wof_film_apply('basic', {'is_effected_in_inventory': True})
        cls.film.wof_film_apply('comp_add', {'part_id': cls.part.id})
        snap = cls.film.wof_matrix_load()
        for line in snap['lines']:
            line['price'] = {'mode': 'uniform', 'general': {'amount': 300, 'readonly': False}, 'sizes': {}}
        cls.film.wof_matrix_save({'lines': snap['lines']})
        cls.film.wof_film_apply('activate')

    def test_editor_sets_film_and_grade_products(self):
        snap = self.film.wof_film_apply('stock_product', {'product_id': self.roll.id})
        self.assertEqual(snap['film']['stock_product']['id'], self.roll.id)
        grade = snap['grades'][0]
        snap = self.film.wof_film_apply('stock_product', {'product_id': self.roll_dark.id, 'grade_id': grade['id']})
        self.assertEqual(snap['grades'][0]['product']['id'], self.roll_dark.id)
        snap = self.film.wof_film_apply('stock_product', {'product_id': False})
        self.assertFalse(snap['film']['stock_product'])

    def test_search_only_returns_stock_products(self):
        names = [p['name'] for p in self.env['wof.film.category'].wof_stock_products_search('رول فيلم')]
        self.assertIn('رول فيلم افتراضي', names)
        self.assertFalse(self.env['wof.film.category'].wof_stock_products_search('زجاج مخزون'))

    def _order_line(self, grade=None):
        partner = self.root['res.partner'].create({'name': 'عميل المخزون', 'mobile': '0500000002'})
        size = self.env['wof.car.size'].search([], limit=1)
        order = self.env['wof.installation.order'].create({
            'partner_id': partner.id, 'vehicle_plate': 'STK 1', 'car_size_id': size.id,
        })
        line = self.env['wof.installation.order.line'].create({
            'order_id': order.id, 'service_type_id': self.activity.id,
            'film_category_id': self.film.id, 'car_part_id': self.part.id,
            'film_category_line_id': grade.id if grade else False,
        })
        return order, line

    def test_order_line_suggests_grade_then_film_product(self):
        self.film.wof_film_apply('stock_product', {'product_id': self.roll.id})
        order, line = self._order_line()
        self.assertTrue(line.film_uses_inventory)
        expected = line.film_category_line_id.product_id or self.roll
        self.assertEqual(line.film_product_id, expected)
        grade = self.film.film_category_line_ids.filtered('active')[:1]
        grade.write({'product_id': self.roll_dark.id})
        order2, line2 = self._order_line(grade)
        self.assertEqual(line2.film_product_id, self.roll_dark)

    def test_required_product_blocks_confirmation(self):
        self.film.wof_film_apply('basic', {'car_film_product_required': True})
        order, line = self._order_line()
        line.film_product_id = False
        with self.assertRaises(ValidationError) as caught:
            order._wof_check_stock_products()
        self.assertIn('الصنف المخزني', str(caught.exception))

    def test_shortage_blocks_unless_setup_allows(self):
        self.film.wof_film_apply('stock_product', {'product_id': self.roll.id})
        order, line = self._order_line()
        line.film_product_id = self.roll
        Order = type(self.env['wof.installation.order'])
        with patch.object(Order, '_wof_negative_blocked', return_value=True):
            self.assertTrue(order._wof_stock_shortages())
            with self.assertRaises(ValidationError):
                order._wof_check_stock_products()
            self.profile.wof_flow_apply('set', {'stock_allow_shortage': True})
            order._wof_check_stock_products()
        # Without the "no negative sales" rule nothing is checked.
        self.profile.wof_flow_apply('set', {'stock_allow_shortage': False})
        order._wof_check_stock_products()
