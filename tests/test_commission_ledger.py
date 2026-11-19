# -*- coding: utf-8 -*-
"""Technician commission ledger: freezing, returns, recalculation and safety."""

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCommissionLedger(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        root = cls.root = cls.env
        groups = ['base.group_user', 'yousentech_wo_v4.group_wo_settings', 'yousentech_wo_v4.group_wo_manager',
                  'account.group_account_invoice', 'sales_team.group_sale_salesman_all_leads',
                  'stock.group_stock_user']
        cls.user = root['res.users'].with_context(no_reset_password=True).create({
            'name': 'مدير العمولات', 'login': 'wof_commission_tester', 'email': 'commission@example.com',
            'groups_id': [(6, 0, [root.ref(g).id for g in groups])],
        })
        env = cls.env = root(user=cls.user)
        profile = env['wof.company.profile']._wof_get_profile() or env['wof.company.profile'].get_or_create_for_company()
        profile.wof_flow_load()
        if profile.state != 'ready':
            profile.wof_flow_apply('set', {'operation_tax_enabled': False})
            profile.wof_flow_apply('activate')
        cls.profile = profile
        service = root['product.product'].create({'name': 'خدمة العمولة', 'type': 'service', 'invoice_policy': 'order'})
        cls.part = root['wof.car.parts'].create({
            'code': 'COM-FRONT', 'name': 'زجاج العمولة', 'part_type': 'car_part', 'product_id': service.id,
        })
        Film = env['wof.film.category']
        cls.activity = env['wof.service.type'].search([('service_options', '=', 'tint'), ('active', '=', True)], limit=1)
        cls.film = Film.browse(Film.wof_film_create(cls.activity.id, 'فيلم العمولة', 'film'))
        cls.film.wof_film_apply('comp_add', {'part_id': cls.part.id})
        cls.set_matrix(100, 'equal')
        cls.film.wof_film_apply('activate')
        company = env.company
        cls.techs = root['hr.employee'].create([
            {'name': 'فني أحمد', 'company_id': company.id}, {'name': 'فني صالح', 'company_id': company.id}])
        Member = root['wof.team.member']
        cls.members = Member.create([
            {'employee_id': cls.techs[0].id, 'company_id': company.id, 'commission_ratio': 50},
            {'employee_id': cls.techs[1].id, 'company_id': company.id, 'commission_ratio': 60},
        ])

    @classmethod
    def set_matrix(cls, commission, distribution):
        snap = cls.film.wof_matrix_load()
        for line in snap['lines']:
            line['price'] = {'mode': 'uniform', 'general': {'amount': 500, 'readonly': False}, 'sizes': {}}
            line['commission'].update({'type': 'fixed', 'policy': 'fixed', 'general': commission,
                                       'distribution': distribution})
        cls.film.wof_matrix_save({'lines': snap['lines']})

    def setUp(self):
        super().setUp()
        self.ledger = self.root['wof.technician.commission']

    def make_order(self):
        partner = self.root['res.partner'].create({'name': 'عميل العمولة', 'mobile': '0500000099'})
        size = self.env['wof.car.size'].search([], limit=1)
        order = self.env['wof.installation.order'].create({
            'partner_id': partner.id, 'vehicle_plate': 'COM 1', 'car_size_id': size.id, 'appointment_at': '2026-12-01',
        })
        self.env['wof.installation.order.line'].create({
            'order_id': order.id, 'service_type_id': self.activity.id,
            'film_category_id': self.film.id, 'car_part_id': self.part.id,
        })
        order.line_ids.with_context(wof_skip_technician_check=True)._write_line_internal(
            {'technician_ids': [(6, 0, self.techs.ids)]})
        return order

    def to_ready(self, order):
        order._transition_write({'state': 'in_progress'})
        order.action_submit_quality()
        self.assertEqual(order.state, 'ready')

    def deliver(self, order):
        self.to_ready(order)
        self.profile.wof_flow_apply('set', {'delivery_unpaid_policy': 'allow'})
        self.addCleanup(self.profile.wof_flow_apply, 'set', {'delivery_unpaid_policy': 'block'})
        order.action_deliver()

    def entries(self, order, states=('pending', 'approved', 'paid')):
        return self.ledger.search([('order_id', '=', order.id), ('state', 'in', states)])

    def amounts(self, order, states=('pending', 'approved', 'paid')):
        result = {}
        for entry in self.entries(order, states):
            result[entry.employee_id.name] = round(result.get(entry.employee_id.name, 0.0) + entry.amount, 2)
        return result

    # ------------------------------------------------------------ lifecycle
    def test_equal_pending_then_frozen_on_delivery(self):
        order = self.make_order()
        self.assertFalse(self.entries(order))
        self.to_ready(order)
        entries = self.entries(order)
        self.assertEqual(set(entries.mapped('state')), {'pending'})
        self.assertEqual(self.amounts(order), {'فني أحمد': 50.0, 'فني صالح': 50.0})
        self.deliver_ready(order)
        entries = self.entries(order)
        self.assertEqual(set(entries.mapped('state')), {'approved'})
        self.assertTrue(all(entries.mapped('approved_at')))
        self.assertTrue(all(entry.source == 'تسليم السيارة' for entry in entries))
        self.assertEqual(order.commission_net, 100.0)

    def deliver_ready(self, order):
        self.profile.wof_flow_apply('set', {'delivery_unpaid_policy': 'allow'})
        self.addCleanup(self.profile.wof_flow_apply, 'set', {'delivery_unpaid_policy': 'block'})
        order.action_deliver()

    def test_weights_50_60_and_rounding(self):
        self.set_matrix(100, 'by_technician_ratio')
        self.addCleanup(self.set_matrix, 100, 'equal')
        order = self.make_order()
        self.deliver(order)
        self.assertEqual(self.amounts(order), {'فني أحمد': 45.45, 'فني صالح': 54.55})
        self.assertEqual(sum(self.entries(order).mapped('amount')), 100.0)
        self.assertEqual(sorted(self.entries(order).mapped('weight')), [50.0, 60.0])
        # Frozen: a later change of weights does not touch approved commissions.
        self.members[0].commission_ratio = 100
        self.assertEqual(self.amounts(order), {'فني أحمد': 45.45, 'فني صالح': 54.55})
        self.assertIn('45.45', order.line_ids.commission_split)

    def test_delivery_requires_finished_tasks(self):
        order = self.make_order()
        self.to_ready(order)
        task = order.task_ids.filtered(lambda rec: rec.employee_id == self.techs[1])
        self.assertTrue(task)
        task.with_context(wof_task_internal=True).write({'done': False})
        self.deliver_ready(order)
        # Only the technician who finished shares the commission.
        self.assertEqual(self.amounts(order, ('approved',)), {'فني أحمد': 100.0})
        cancelled = self.entries(order, ('cancelled',))
        self.assertEqual(cancelled.employee_id, self.techs[1])

    def test_order_cancel_cancels_unpaid(self):
        order = self.make_order()
        self.to_ready(order)
        order.write({'cancellation_reason': 'اختبار'})
        order.action_cancel()
        self.assertFalse(self.entries(order))
        self.assertEqual(len(self.entries(order, ('cancelled',))), 2)

    # ------------------------------------------------------------ returns
    def invoice(self, order):
        order.action_create_invoice()
        invoice = order.invoice_id
        if invoice.state != 'posted':
            invoice.action_post()
        return invoice

    def refund(self, invoice, quantity=None):
        refund = invoice._reverse_moves([{'ref': 'مرتجع اختبار'}])
        if quantity is not None:
            line = refund.invoice_line_ids.filtered(lambda aml: aml.sale_line_ids.wof_order_line_id)
            line.quantity = quantity
        refund.action_post()
        return refund

    def test_credit_note_reverses_with_the_frozen_split(self):
        order = self.make_order()
        self.deliver(order)
        invoice = self.invoice(order)
        # Settings change after approval: the return still uses the frozen split.
        self.set_matrix(100, 'by_technician_ratio')
        self.addCleanup(self.set_matrix, 100, 'equal')
        refund = self.refund(invoice, quantity=0.5)
        reversals = self.entries(order).filtered(lambda entry: entry.entry_type == 'reversal')
        self.assertEqual(sorted(reversals.mapped('amount')), [-25.0, -25.0])
        self.assertEqual(reversals.refund_move_id, refund)
        self.assertEqual(self.amounts(order), {'فني أحمد': 25.0, 'فني صالح': 25.0})
        # Undoing the credit note gives the commission back.
        refund.button_draft()
        self.assertEqual(self.amounts(order), {'فني أحمد': 50.0, 'فني صالح': 50.0})

    def test_full_credit_note_adds_negative_entries(self):
        order = self.make_order()
        self.deliver(order)
        refund = self.refund(self.invoice(order))
        reversals = self.entries(order).filtered(lambda entry: entry.entry_type == 'reversal')
        self.assertEqual(sorted(reversals.mapped('amount')), [-50.0, -50.0])
        self.assertEqual(reversals.refund_move_id, refund)
        self.assertEqual(sum(self.entries(order).mapped('amount')), 0.0)
        refund._wof_commission_apply_refund()  # applied once only
        self.assertEqual(len(self.entries(order).filtered(lambda entry: entry.entry_type == 'reversal')), 2)
        refund.button_draft()
        self.assertEqual(self.amounts(order), {'فني أحمد': 50.0, 'فني صالح': 50.0})
        refund.action_post()  # posting again reverses again
        self.assertEqual(sum(self.entries(order).mapped('amount')), 0.0)

    def test_credit_note_without_sale_link(self):
        """A credit note whose lines lost the sale order link is matched by product."""
        order = self.make_order()
        self.deliver(order)
        invoice = self.invoice(order)
        refund = invoice._reverse_moves([{'ref': 'بدون ربط'}])
        refund.invoice_line_ids.write({'sale_line_ids': [(5, 0, 0)]})
        refund.action_post()
        self.assertEqual(sum(self.entries(order).mapped('amount')), 0.0)

    def test_invoice_event_approves_without_task_check(self):
        self.root['wof.film.category'].browse(self.film.id).write({'commission_event': 'invoice'})
        self.addCleanup(self.root['wof.film.category'].browse(self.film.id).write, {'commission_event': 'delivery'})
        order = self.make_order()
        self.to_ready(order)
        order.task_ids[:1].with_context(wof_task_internal=True).write({'done': False})
        invoice = self.invoice(order)
        self.assertEqual(set(self.entries(order).mapped('state')), {'approved'})
        self.assertEqual(self.amounts(order), {'فني أحمد': 50.0, 'فني صالح': 50.0})
        self.assertIn(invoice.name, self.entries(order)[0].source)
        invoice.button_draft()
        self.assertEqual(set(self.entries(order).mapped('state')), {'pending'})

    # -------------------------------------------------------- recalculation
    def test_recalculation_replaces_unpaid_and_adjusts_paid(self):
        order = self.make_order()
        self.deliver(order)
        with self.assertRaises(ValidationError):
            order._wof_commission_recalc_apply('')
        self.set_matrix(110, 'by_technician_ratio')
        self.addCleanup(self.set_matrix, 100, 'equal')
        action = order.action_open_commission_recalc()
        wizard = self.env['wof.commission.recalc.wizard'].browse(action['res_id'])
        self.assertEqual(sorted(wizard.line_ids.mapped('new_amount')), [50.0, 60.0])
        wizard.reason = 'تصحيح التوزيع'
        wizard.action_confirm()
        self.assertEqual(self.amounts(order), {'فني أحمد': 50.0, 'فني صالح': 60.0})
        # Ahmed keeps 50 (unchanged, untouched); Saleh's entry is replaced.
        self.assertEqual(self.entries(order, ('replaced',)).employee_id, self.techs[1])
        self.assertEqual(order.line_ids.configured_commission, 110.0)
        # A paid commission is never changed: the difference becomes an adjustment.
        engine = self.env['wof.commission.engine']._wof_ledger()
        engine.browse(self.entries(order).ids).write({'state': 'paid'})
        self.set_matrix(100, 'equal')
        order._wof_commission_recalc_apply('رجوع للتساوي')
        adjustments = self.entries(order).filtered(lambda entry: entry.entry_type == 'adjustment')
        self.assertEqual(adjustments.mapped('amount'), [-10.0])
        self.assertEqual(self.amounts(order), {'فني أحمد': 50.0, 'فني صالح': 50.0})
        self.assertEqual(set(self.entries(order).filtered(lambda e: e.entry_type == 'normal').mapped('state')), {'paid'})

    def test_manual_adjustment(self):
        order = self.make_order()
        self.deliver(order)
        wizard = self.env['wof.commission.adjust.wizard'].with_context(default_order_id=order.id).create({
            'employee_id': self.techs[0].id, 'amount': -15, 'reason': 'تلف أثناء التركيب'})
        wizard.action_confirm()
        self.assertEqual(self.amounts(order)['فني أحمد'], 35.0)

    # --------------------------------------------------------------- safety
    def test_ledger_is_read_only(self):
        order = self.make_order()
        self.to_ready(order)
        entry = self.env['wof.technician.commission'].search([('order_id', '=', order.id)], limit=1)
        self.assertTrue(entry)  # the manager reads it
        with self.assertRaises(AccessError):
            entry.write({'amount': 999})
        with self.assertRaises(AccessError):
            self.env['wof.technician.commission'].create({'employee_id': self.techs[0].id, 'company_id': order.company_id.id})
        with self.assertRaises(UserError):
            entry.unlink()
        technician = self.root['res.users'].with_context(no_reset_password=True).create({
            'name': 'فني بلا صلاحية', 'login': 'wof_commission_tech', 'email': 'tech@example.com',
            'groups_id': [(6, 0, [self.root.ref('yousentech_wo_v4.group_wo_technician').id])],
        })
        with self.assertRaises(AccessError):
            self.ledger.with_user(technician).search([])

    def test_ratio_change_is_tracked(self):
        emp = self.root['hr.employee'].create({'name': 'فني التتبع', 'company_id': self.env.company.id})
        member = self.root['wof.team.member'].create({
            'employee_id': emp.id, 'company_id': self.env.company.id, 'commission_ratio': 50})
        self.env.flush_all()
        self.env.cr.precommit.run()
        member.commission_ratio = 70
        self.env.flush_all()
        self.env.cr.precommit.run()
        self.assertEqual(member.message_ids.tracking_value_ids.mapped('new_value_float'), [70.0])

    def test_free_service_setting(self):
        self.profile.wof_flow_apply('set', {'commission_free_service': 'none'})
        self.addCleanup(self.profile.wof_flow_apply, 'set', {'commission_free_service': 'commission'})
        order = self.make_order()
        order.line_ids._write_line_internal({'unit_price': 0.0})
        self.assertEqual(order.line_ids._wof_commission_total(), 0.0)
        self.to_ready(order)
        self.assertFalse(self.entries(order))

    # ------------------------------------------------------- service areas
    def make_area(self, rear_rule='equal'):
        Parts = self.root['wof.car.parts']
        kids = Parts
        for code, name in (('CA-FRONT', 'زجاج أمامي'), ('CA-REAR', 'زجاج خلفي')):
            kids |= Parts.create({'code': code, 'name': name, 'part_type': 'car_part',
                                  'product_id': self.root['product.product'].create({'name': name, 'type': 'service'}).id})
        area = Parts.create({'code': 'CA-AREA', 'name': 'منطقة كامل السيارة', 'part_type': 'service_area',
                             'product_id': self.root['product.product'].create({'name': 'منطقة', 'type': 'service'}).id})
        self.root['wof.service.area.template'].create({'name': 'كامل', 'service_area_id': area.id,
                                                       'component_ids': [(6, 0, kids.ids)], 'is_default': True})
        film = self.film
        film.wof_film_apply('comp_add', {'part_id': area.id})
        snap = film.wof_matrix_load()
        for line in snap['lines']:
            line['price'] = {'mode': 'uniform', 'general': {'amount': 500, 'readonly': False}, 'sizes': {}}
            if line.get('children'):
                line['commission'].update({'source': 'from_parts', 'distribution': 'by_part'})
                for child, value, rule in zip(line['children'], (10, 20), ('equal', rear_rule)):
                    child['commission'].update({'type': 'fixed', 'policy': 'fixed', 'general': value,
                                                'distribution': rule})
            else:
                line['commission'].update({'type': 'fixed', 'policy': 'fixed', 'general': 100, 'distribution': 'equal'})
        film.wof_matrix_save({'lines': snap['lines']})
        return area, kids

    def test_by_part_uses_each_part_commission(self):
        area, kids = self.make_area()
        partner = self.root['res.partner'].create({'name': 'عميل المنطقة', 'mobile': '0500000098'})
        size = self.env['wof.car.size'].search([], limit=1)
        order = self.env['wof.installation.order'].create({
            'partner_id': partner.id, 'vehicle_plate': 'AREA 1', 'car_size_id': size.id, 'appointment_at': '2026-12-01'})
        order.wof_add_services([{'film_id': self.film.id, 'part_id': area.id}])
        line = order.line_ids
        self.assertEqual(line.configured_commission, 30.0)
        front = line.part_line_ids.filtered(lambda rec: rec.part_id == kids[0])
        rear = line.part_line_ids - front
        third = self.root['hr.employee'].create({'name': 'فني ثالث', 'company_id': self.env.company.id})
        self.root['wof.team.member'].create({'employee_id': third.id, 'company_id': self.env.company.id})
        # Ahmed alone on the front (10); Ahmed, Saleh and the third on the rear (20).
        line.wof_area_update(front.ids, {'technician_ids': [self.techs[0].id]})
        line.wof_area_update(rear.ids, {'technician_ids': [self.techs[0].id, self.techs[1].id, third.id]})
        self.to_ready(order)
        entries = self.entries(order)
        ahmed = entries.filtered(lambda entry: entry.employee_id == self.techs[0])
        self.assertEqual(ahmed.filtered(lambda entry: entry.car_part_id == kids[0]).amount, 10.0)
        self.assertIn(ahmed.filtered(lambda entry: entry.car_part_id == kids[1]).amount, (6.66, 6.67))
        self.assertEqual(round(sum(entries.filtered(lambda entry: entry.car_part_id == kids[1]).mapped('amount')), 2), 20.0)
        self.assertEqual(round(sum(entries.mapped('amount')), 2), 30.0)
        rear_entry = entries.filtered(lambda entry: entry.car_part_id == kids[1])[:1]
        self.assertEqual((rear_entry.part_share, rear_entry.part_technician_count), (20.0, 3))
        self.assertIn('زجاج خلفي', order.commission_summary_html)

    def test_area_bulk_technician_adds_and_removes(self):
        area, _kids = self.make_area()
        partner = self.root['res.partner'].create({'name': 'عميل المنطقة', 'mobile': '0500000097'})
        size = self.env['wof.car.size'].search([], limit=1)
        order = self.env['wof.installation.order'].create({
            'partner_id': partner.id, 'vehicle_plate': 'AREA 2', 'car_size_id': size.id, 'appointment_at': '2026-12-01'})
        order.wof_add_services([{'film_id': self.film.id, 'part_id': area.id}])
        line = order.line_ids
        parts = line.part_line_ids
        line.wof_area_update(parts.ids, {'toggle_technician_id': self.techs[0].id})
        line.wof_area_update(parts.ids, {'toggle_technician_id': self.techs[1].id})
        for part in parts:
            self.assertEqual(part.technician_ids, self.techs)  # added, not replaced
        line.wof_area_update(parts.ids, {'toggle_technician_id': self.techs[0].id})
        for part in parts:
            self.assertEqual(part.technician_ids, self.techs[1])  # on all parts: removed from all

    def test_part_inside_area_cannot_be_added_alone(self):
        area, kids = self.make_area()
        self.film.wof_film_apply('comp_add', {'part_id': kids[0].id})
        snap = self.film.wof_matrix_load()
        for line in snap['lines']:
            line['price'] = {'mode': 'uniform', 'general': {'amount': 500, 'readonly': False}, 'sizes': {}}
        self.film.wof_matrix_save({'lines': snap['lines']})
        partner = self.root['res.partner'].create({'name': 'عميل التكرار', 'mobile': '0500000096'})
        size = self.env['wof.car.size'].search([], limit=1)
        order = self.env['wof.installation.order'].create({
            'partner_id': partner.id, 'vehicle_plate': 'AREA 3', 'car_size_id': size.id, 'appointment_at': '2026-12-01'})
        order.wof_add_services([{'film_id': self.film.id, 'part_id': area.id}])
        with self.assertRaises(ValidationError):
            order.wof_add_services([{'film_id': self.film.id, 'part_id': kids[0].id}])

    def test_year_typed_on_the_order(self):
        Year = self.env['wof.car.manufactory.year']
        year_id, _name = Year.name_create(' 2031 ')
        self.assertEqual(Year.browse(year_id).code, '2031')
        self.assertEqual(Year.name_create('2031')[0], year_id)
        with self.assertRaises(ValidationError):
            Year.name_create('31')

    def test_part_follows_its_own_distribution(self):
        """Inside an area, each part splits its commission the way the part is set up."""
        area, kids = self.make_area(rear_rule='by_technician_ratio')
        partner = self.root['res.partner'].create({'name': 'عميل التوزيع', 'mobile': '0500000095'})
        size = self.env['wof.car.size'].search([], limit=1)
        order = self.env['wof.installation.order'].create({
            'partner_id': partner.id, 'vehicle_plate': 'AREA 4', 'car_size_id': size.id, 'appointment_at': '2026-12-01'})
        order.wof_add_services([{'film_id': self.film.id, 'part_id': area.id}])
        line = order.line_ids
        front = line.part_line_ids.filtered(lambda rec: rec.part_id == kids[0])
        rear = line.part_line_ids - front
        line.wof_area_update(front.ids, {'technician_ids': [self.techs[0].id]})
        line.wof_area_update(rear.ids, {'technician_ids': self.techs.ids})
        self.to_ready(order)
        entries = self.entries(order)
        rear_entries = entries.filtered(lambda entry: entry.car_part_id == kids[1])
        # Rear 20 by weights 50 / 60: 9.09 and 10.91; front 10 to Ahmed alone.
        self.assertEqual(sorted(rear_entries.mapped('amount')), [9.09, 10.91])
        self.assertEqual(set(rear_entries.mapped('part_rule')), {'by_technician_ratio'})
        self.assertEqual(rear_entries.filtered(lambda entry: entry.employee_id == self.techs[0]).weight_total, 110.0)
        self.assertEqual(self.amounts(order), {'فني أحمد': 19.09, 'فني صالح': 10.91})
        self.assertIn('وزنه 50 من 110', order.commission_summary_html)
        # The area itself may still split everything equally between all its technicians.
        snap = self.film.wof_matrix_load()
        for item in snap['lines']:
            if item.get('children'):
                item['commission']['distribution'] = 'equal'
        self.film.wof_matrix_save({'lines': snap['lines']})
        rule, plan = line._wof_commission_plan()
        self.assertEqual(rule, 'equal')
        self.assertEqual(sorted(amount for amount, *_rest in plan.values()), [15.0, 15.0])

