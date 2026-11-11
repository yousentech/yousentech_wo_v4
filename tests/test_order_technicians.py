# -*- coding: utf-8 -*-
"""Technicians are HR employees; branches see their own orders; transfers stay safe."""

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestOrderTechnicians(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        root = cls.root = cls.env
        cls.company_a = root.company
        cls.company_b = root['res.company'].create({'name': 'فرع التركيب ب'})
        Users = root['res.users'].with_context(no_reset_password=True)
        both = [(6, 0, [cls.company_a.id, cls.company_b.id])]
        cls.manager = Users.create({
            'name': 'مدير الفرع أ', 'login': 'wof_tech_manager', 'email': 'tm@example.com',
            'company_id': cls.company_a.id, 'company_ids': [(6, 0, [cls.company_a.id])],
            'groups_id': [(6, 0, [root.ref('base.group_user').id, root.ref('yousentech_wo_v4.group_wo_settings').id])],
        })
        cls.tech_user = Users.create({
            'name': 'فني متنقل', 'login': 'wof_moving_tech', 'email': 'mt@example.com',
            'company_id': cls.company_a.id, 'company_ids': both,
            'groups_id': [(6, 0, [root.ref('base.group_user').id, root.ref('yousentech_wo_v4.group_wo_technician').id])],
        })
        cls.tech = root['hr.employee'].create({
            'name': 'فني متنقل', 'company_id': cls.company_a.id, 'user_id': cls.tech_user.id, 'is_wof_technician': True,
        })
        cls.other_branch_tech = root['hr.employee'].create({
            'name': 'فني الفرع ب', 'company_id': cls.company_b.id, 'is_wof_technician': True,
        })
        cls.not_tech = root['hr.employee'].create({'name': 'محاسب', 'company_id': cls.company_a.id})

        env = cls.env = root(user=cls.manager, context={'allowed_company_ids': [cls.company_a.id]})
        profile = env['wof.company.profile']._wof_get_profile() or env['wof.company.profile'].get_or_create_for_company()
        profile.wof_flow_load()
        if profile.state != 'ready':
            profile.wof_flow_apply('set', {'operation_tax_enabled': False})
            profile.wof_flow_apply('activate')

    def make_order(self):
        partner = self.root['res.partner'].create({'name': 'عميل الفنيين', 'mobile': '0500000011'})
        size = self.env['wof.car.size'].search([], limit=1)
        return self.env['wof.installation.order'].create({
            'partner_id': partner.id, 'vehicle_plate': 'TEC 1', 'car_size_id': size.id,
        })

    def test_only_branch_technicians_can_be_chosen(self):
        order = self.make_order()
        order.write({'technician_ids': [(0, 0, {'employee_id': self.tech.id})]})
        self.assertEqual(order.technician_ids.employee_id, self.tech)
        self.assertEqual(order.technician_ids.user_id, self.tech_user)
        self.assertEqual(order.technician_names, 'فني متنقل')
        with self.assertRaises(ValidationError):
            order.write({'technician_ids': [(0, 0, {'employee_id': self.not_tech.id})]})
        with self.assertRaises(ValidationError):
            order.write({'technician_ids': [(0, 0, {'employee_id': self.other_branch_tech.id})]})
        found = self.env['hr.employee'].search([
            ('is_wof_technician', '=', True), ('company_id', 'in', [order.company_id.id, False]),
        ])
        self.assertIn(self.tech, found)
        self.assertNotIn(self.other_branch_tech, found)

    def test_transfer_keeps_old_orders_working(self):
        order = self.make_order()
        order.write({'technician_ids': [(0, 0, {'employee_id': self.tech.id})]})
        # The technician moves to branch B.
        self.root['hr.employee'].browse(self.tech.id).company_id = self.company_b
        order.invalidate_recordset()
        order.technician_ids.invalidate_recordset()
        # Branch A's manager cannot see branch B employees, yet the order still shows the name.
        self.assertFalse(self.env['hr.employee'].search([('id', '=', self.tech.id)]))
        data = order.web_read({
            'technician_ids': {'fields': {'display_name': {}, 'employee_id': {'fields': {'display_name': {}}}}},
            'technician_names': {},
        })[0]
        self.assertEqual(data['technician_names'], 'فني متنقل')
        self.assertEqual(data['technician_ids'][0]['display_name'], 'فني متنقل')
        self.assertEqual(data['technician_ids'][0]['employee_id']['display_name'], 'فني متنقل')
        # Saving the order again raises nothing about the other branch.
        order.write({'customer_notes': 'بعد النقل'})
        self.assertTrue(order._wof_is_assigned_technician(self.tech_user))

    def test_technician_sees_assigned_orders_only(self):
        order = self.make_order()
        other = self.make_order()
        order.write({'technician_ids': [(0, 0, {'employee_id': self.tech.id})]})
        Orders = self.root['wof.installation.order'].with_user(self.tech_user).with_context(
            allowed_company_ids=[self.company_a.id])
        visible = Orders.search([('id', 'in', (order | other).ids)])
        self.assertEqual(visible, order)

    def test_orders_follow_user_companies(self):
        order = self.make_order()
        outsider = self.root['res.users'].with_context(no_reset_password=True).create({
            'name': 'مدير الفرع ب', 'login': 'wof_branch_b', 'email': 'bb@example.com',
            'company_id': self.company_b.id, 'company_ids': [(6, 0, [self.company_b.id])],
            'groups_id': [(6, 0, [self.root.ref('base.group_user').id, self.root.ref('yousentech_wo_v4.group_wo_manager').id])],
        })
        Orders = self.root['wof.installation.order'].with_user(outsider).with_context(allowed_company_ids=[self.company_b.id])
        self.assertFalse(Orders.search([('id', '=', order.id)]))
        with self.assertRaises(AccessError):
            Orders.browse(order.id).read(['name'])

    def test_remove_unused_technician(self):
        order = self.make_order()
        order.write({'technician_ids': [(0, 0, {'employee_id': self.tech.id})]})
        order.write({'technician_ids': [(2, order.technician_ids.id)]})
        self.assertFalse(order.technician_ids)
        self.assertFalse(order.technician_names)
