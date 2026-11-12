# -*- coding: utf-8 -*-
"""Technicians per service (HR employees), people of the order, branch rules and transfers."""

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
        Employee = root['hr.employee']
        cls.manager_employee = Employee.create({'name': 'مدير الفرع أ', 'company_id': cls.company_a.id, 'user_id': cls.manager.id})
        cls.tech = Employee.create({
            'name': 'فني متنقل', 'company_id': cls.company_a.id, 'user_id': cls.tech_user.id, 'is_wof_technician': True,
        })
        cls.tech_2 = Employee.create({'name': 'فني ثانٍ', 'company_id': cls.company_a.id, 'is_wof_technician': True})
        cls.other_branch_tech = Employee.create({
            'name': 'فني الفرع ب', 'company_id': cls.company_b.id, 'is_wof_technician': True,
        })
        cls.not_tech = Employee.create({'name': 'محاسب', 'company_id': cls.company_a.id})

        env = cls.env = root(user=cls.manager, context={'allowed_company_ids': [cls.company_a.id]})
        profile = env['wof.company.profile']._wof_get_profile() or env['wof.company.profile'].get_or_create_for_company()
        profile.wof_flow_load()
        if profile.state != 'ready':
            profile.wof_flow_apply('set', {'operation_tax_enabled': False})
            profile.wof_flow_apply('activate')
        profile.operation_allow_multiple_technicians = True
        cls.profile = profile

        service = root['product.product'].create({'name': 'خدمة فنيين', 'type': 'service'})
        cls.part = root['wof.car.parts'].create({
            'code': 'TEC-PART', 'name': 'جزء الفنيين', 'part_type': 'car_part', 'product_id': service.id,
        })
        Film = env['wof.film.category']
        cls.activity = env['wof.service.type'].search([('service_options', '=', 'tint'), ('active', '=', True)], limit=1)
        cls.film = Film.browse(Film.wof_film_create(cls.activity.id, 'فيلم الفنيين', 'film'))
        cls.film.wof_film_apply('comp_add', {'part_id': cls.part.id})
        snap = cls.film.wof_matrix_load()
        for line in snap['lines']:
            line['price'] = {'mode': 'uniform', 'general': {'amount': 100, 'readonly': False}, 'sizes': {}}
        cls.film.wof_matrix_save({'lines': snap['lines']})
        cls.film.wof_film_apply('activate')

    def make_order(self):
        partner = self.root['res.partner'].create({'name': 'عميل الفنيين', 'mobile': '0500000011'})
        size = self.env['wof.car.size'].search([], limit=1)
        order = self.env['wof.installation.order'].create({
            'partner_id': partner.id, 'vehicle_plate': 'TEC 1', 'car_size_id': size.id,
        })
        self.env['wof.installation.order.line'].create({
            'order_id': order.id, 'service_type_id': self.activity.id,
            'film_category_id': self.film.id, 'car_part_id': self.part.id,
        })
        return order

    def test_people_defaults(self):
        order = self.make_order()
        self.assertEqual(order.created_by_id, self.manager)
        self.assertEqual(order.advisor_id, self.manager_employee)

    def test_technicians_per_service(self):
        order = self.make_order()
        line = order.line_ids
        line.write({'technician_ids': [(4, self.tech.id), (4, self.tech_2.id)]})
        self.assertEqual(line.technician_ids, self.tech | self.tech_2)
        self.assertEqual(line.technician_names, 'فني متنقل، فني ثانٍ')
        self.assertEqual(order.technician_names, 'فني متنقل، فني ثانٍ')
        self.assertTrue(order._wof_is_assigned_technician(self.tech_user))
        with self.assertRaises(ValidationError):
            line.write({'technician_ids': [(4, self.not_tech.id)]})
        with self.assertRaises(ValidationError):
            line.write({'technician_ids': [(4, self.other_branch_tech.id)]})

    def test_single_technician_setting(self):
        self.profile.operation_allow_multiple_technicians = False
        order = self.make_order()
        order.line_ids.write({'technician_ids': [(4, self.tech.id)]})
        with self.assertRaises(ValidationError):
            order.line_ids.write({'technician_ids': [(4, self.tech_2.id)]})

    def test_transfer_keeps_old_orders_working(self):
        order = self.make_order()
        line = order.line_ids
        line.write({'technician_ids': [(4, self.tech.id)]})
        # The technician moves to branch B.
        self.root['hr.employee'].browse(self.tech.id).company_id = self.company_b
        self.env.invalidate_all()
        self.assertFalse(self.env['hr.employee'].search([('id', '=', self.tech.id)]))
        # Stored names still show him; adding another technician keeps him.
        self.assertEqual(line.technician_names, 'فني متنقل')
        line.write({'technician_ids': [(4, self.tech_2.id)]})
        self.assertEqual(line.technician_names, 'فني متنقل، فني ثانٍ')
        self.env.flush_all()
        self.env.cr.execute('SELECT employee_id FROM wof_order_line_technician_rel WHERE line_id = %s', (line.id,))
        self.assertIn(self.tech.id, [row[0] for row in self.env.cr.fetchall()])
        order.write({'customer_notes': 'بعد النقل'})
        self.assertEqual(order.technician_names, 'فني متنقل، فني ثانٍ')

    def test_technician_adds_only_himself(self):
        order = self.make_order()
        line = order.line_ids
        line.write({'technician_ids': [(4, self.tech.id)]})
        tech_line = line.with_user(self.tech_user).with_context(allowed_company_ids=[self.company_a.id])
        with self.assertRaises(AccessError):
            tech_line.write({'technician_ids': [(4, self.tech_2.id)]})

    def test_technician_sees_assigned_orders_only(self):
        order = self.make_order()
        other = self.make_order()
        order.line_ids.write({'technician_ids': [(4, self.tech.id)]})
        Orders = self.root['wof.installation.order'].with_user(self.tech_user).with_context(
            allowed_company_ids=[self.company_a.id])
        self.assertEqual(Orders.search([('id', 'in', (order | other).ids)]), order)

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

    def test_change_branch_needs_the_right(self):
        order = self.make_order()
        with self.assertRaises(ValidationError):
            order.write({'company_id': self.company_b.id})

    def test_change_branch_on_draft_order(self):
        self.manager.company_ids = [(4, self.company_b.id)]
        self.manager.groups_id = [(4, self.root.ref('yousentech_wo_v4.group_wo_change_branch').id)]
        env = self.env(context={'allowed_company_ids': [self.company_a.id, self.company_b.id]})
        order = self.make_order().with_env(env)
        order.line_ids.write({'technician_ids': [(4, self.tech_2.id)]})
        with self.assertRaises(ValidationError):
            order.write({'company_id': self.company_b.id})  # a service still has a branch A technician
        order.line_ids.write({'technician_ids': [(3, self.tech_2.id)]})
        order.write({'company_id': self.company_b.id})
        self.assertEqual(order.company_id, self.company_b)
        order.line_ids.write({'technician_ids': [(4, self.other_branch_tech.id)]})
        self.assertEqual(order.technician_names, 'فني الفرع ب')
        with self.assertRaises(ValidationError):
            order.advisor_id = self.manager_employee  # branch A employee on a branch B order

    def test_salesman_of_the_branch(self):
        Salesman = self.root['salesman']
        here = Salesman.create({'name': 'مندوب أ', 'sale_user': self.manager.id})
        moved = Salesman.create({'name': 'مندوب منقول'})
        self.root['salesman.assignments'].create({'salesman_id': moved.id, 'company_id': self.company_b.id})
        order = self.make_order()
        self.assertIn(here, order.salesman_candidate_ids)
        self.assertNotIn(moved, order.salesman_candidate_ids)
        self.assertEqual(order.salesperson_id, here)  # default: the user's own salesman
        with self.assertRaises(ValidationError):
            order.salesperson_id = moved

    def test_supervisor_must_be_flagged(self):
        order = self.make_order()
        with self.assertRaises(ValidationError):
            order.supervisor_id = self.manager_employee
        self.manager_employee.is_wof_supervisor = True
        order.supervisor_id = self.manager_employee
        self.assertEqual(order.supervisor_id, self.manager_employee)

    def test_vehicle_record_and_owner_history(self):
        size = self.env['wof.car.size'].search([], limit=1)
        first = self.root['res.partner'].create({'name': 'المالك الأول'})
        second = self.root['res.partner'].create({'name': 'المالك الثاني'})
        Order = self.env['wof.installation.order']
        order1 = Order.create({'partner_id': first.id, 'vehicle_plate': 'abj  1234', 'car_size_id': size.id,
                               'vehicle_color': 'أبيض'})
        self.assertEqual(order1.vehicle_plate, 'ABJ 1234')
        vehicle = order1.vehicle_id
        self.assertTrue(vehicle)
        self.assertEqual(vehicle.partner_id, first)
        self.assertEqual(vehicle.color, 'أبيض')
        self.assertEqual(len(vehicle.owner_ids), 1)
        # Sold: the same plate on an order of another customer moves ownership.
        order2 = Order.create({'partner_id': second.id, 'vehicle_plate': 'ABJ 1234', 'car_size_id': size.id})
        self.assertEqual(order2.vehicle_id, vehicle)
        self.assertEqual(vehicle.partner_id, second)
        self.assertEqual(len(vehicle.owner_ids), 2)
        self.assertTrue(vehicle.owner_ids.filtered(lambda line: line.partner_id == first).date_end)
        self.assertEqual(vehicle.order_ids, order1 | order2)
        # The first order keeps its own snapshot.
        self.assertEqual(order1.partner_id, first)
        self.assertEqual(order1.vehicle_color, 'أبيض')

    def test_plate_moved_to_another_car(self):
        size = self.env['wof.car.size'].search([], limit=1)
        partner = self.root['res.partner'].create({'name': 'عميل اللوحة'})
        Order = self.env['wof.installation.order']
        old = Order.create({'partner_id': partner.id, 'vehicle_plate': 'BDR 55', 'vehicle_vin': 'VIN1',
                            'car_size_id': size.id}).vehicle_id
        new_order = Order.create({'partner_id': partner.id, 'vehicle_plate': 'BDR 55', 'vehicle_vin': 'VIN2',
                                  'car_size_id': size.id})
        self.assertNotEqual(new_order.vehicle_id, old)
        self.assertFalse(old.plate)
        self.assertEqual(new_order.vehicle_id.vin, 'VIN2')
