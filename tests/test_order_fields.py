# -*- coding: utf-8 -*-
"""The installation order follows the setup's field policy (required / optional /
hidden), checking each field at the stage it belongs to."""

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestOrderFields(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        groups = ['base.group_user', 'yousentech_wo_v4.group_wo_settings',
                  'yousentech_wo_v4.group_wo_manager']
        user = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'مدير حقول الأمر', 'login': 'wof_order_fields_tester',
            'groups_id': [(6, 0, [cls.env.ref(g).id for g in groups])],
        })
        root = cls.root = cls.env
        env = cls.env = cls.env(user=user)
        profile = env['wof.company.profile']._wof_get_profile()
        if not profile:
            profile = env['wof.company.profile'].get_or_create_for_company()
        profile.wof_flow_load()
        if profile.state != 'ready':
            profile.wof_flow_apply('set', {'operation_tax_enabled': False})
            profile.wof_flow_apply('activate')
        cls.profile = profile
        cls.lines = {line.field_key: line for line in profile.operation_field_line_ids}
        partner = root['res.partner'].create({'name': 'عميل الحقول', 'mobile': '0500000001'})
        size = env['wof.car.size'].search([], limit=1)
        cls.order = env['wof.installation.order'].create({
            'partner_id': partner.id, 'vehicle_plate': 'ABC 1', 'car_size_id': size.id,
        })

    def set_state(self, key, state):
        self.profile.wof_flow_apply('field', {'id': self.lines[key].id, 'state': state})

    def test_new_fields_are_in_the_setup_list(self):
        for key in ('manufacturer', 'model', 'agency', 'customer_category', 'supervisor',
                    'sticker_removal', 'completion_date', 'salesperson'):
            self.assertIn(key, self.lines)

    def test_policy_drives_hidden_and_required_lists(self):
        self.set_state('agency', 'hid')
        self.set_state('color', 'req')
        self.order.invalidate_recordset(['wof_hidden_fields', 'wof_required_fields'])
        self.assertIn(',agency,', self.order.wof_hidden_fields)
        self.assertIn(',color,', self.order.wof_required_fields)
        self.assertNotIn(',color,', self.order.wof_hidden_fields)

    def test_confirm_stage_lists_all_missing_in_one_message(self):
        self.set_state('color', 'req')
        self.set_state('vin', 'req')
        with self.assertRaises(ValidationError) as caught:
            self.order._wof_check_stage_fields('confirm')
        message = str(caught.exception)
        self.assertIn('اللون', message)
        self.assertIn('الشاصي', message)
        self.assertIn('عند تأكيد الأمر', message)

    def test_optional_plate_and_mobile_are_not_demanded(self):
        self.set_state('plate', 'opt')
        self.set_state('mobile', 'opt')
        for key in ('vin', 'color', 'manufacturer', 'model', 'manufacture_year', 'agency',
                    'customer_category', 'delivery_time', 'salesperson', 'supervisor'):
            self.set_state(key, 'opt')
        self.order.write({'vehicle_plate': False})
        self.root['res.partner'].browse(self.order.partner_id.id).mobile = False
        self.order._wof_check_stage_fields('confirm')

    def test_intake_fields_checked_at_intake_only(self):
        self.set_state('odometer', 'req')
        self.set_state('sticker_removal', 'req')
        for key in ('vin', 'color', 'manufacturer', 'model', 'manufacture_year', 'agency',
                    'customer_category', 'delivery_time', 'salesperson', 'supervisor'):
            self.set_state(key, 'opt')
        self.order._wof_check_stage_fields('confirm')
        with self.assertRaises(ValidationError) as caught:
            self.order._wof_check_stage_fields('intake')
        self.assertIn('العداد', str(caught.exception))
        self.assertIn('إزالة اللواصق', str(caught.exception))
        self.order.write({'odometer': 12000, 'sticker_removal': 'not_needed'})
        self.order._wof_check_stage_fields('intake')
