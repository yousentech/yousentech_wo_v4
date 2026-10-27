# -*- coding: utf-8 -*-
"""Runtime tests for the guided setup screen service (wof_flow_load / wof_flow_apply).

Run on a test database:
    odoo-bin -d <db> -u yousentech_wo_v4 --test-enable --test-tags /yousentech_wo_v4:TestSetupFlow --stop-after-init
"""

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSetupFlow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # One setup profile serves every branch: start these tests from a fresh one.
        cls.env['wof.company.profile'].search([]).unlink()
        cls.company = cls.env['res.company'].create({'name': 'شركة اختبار التهيئة'})
        cls.user = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'مسؤول تهيئة الاختبار',
            'login': 'wof_setup_flow_tester',
            'company_id': cls.company.id,
            'company_ids': [(6, 0, [cls.company.id])],
            'groups_id': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('yousentech_wo_v4.group_wo_settings').id,
            ])],
        })
        cls.Profile = cls.env['wof.company.profile'].with_user(cls.user).with_company(cls.company)

    def setUp(self):
        super().setUp()
        self.profile = self.Profile.get_or_create_for_company(self.company)
        self.snap = self.profile.wof_flow_load()

    def apply(self, op, payload=None):
        self.snap = self.profile.wof_flow_apply(op, payload or {})
        return self.snap

    def test_load_prepares_defaults_and_starts(self):
        self.assertEqual(self.snap['state'], 'in_progress')
        self.assertEqual({a['type'] for a in self.snap['activities']}, {'tint', 'general'})
        self.assertEqual([s['code'] for s in self.snap['sizes']], ['SMALL', 'MEDIUM', 'LARGE', 'SUV'])
        self.assertEqual([s['value'] for s in self.snap['tint']['shades']], ['00', '01', '02', '03', '04'])
        self.assertEqual(len(self.snap['fields']), 10)
        action = self.profile._wizard_action()
        self.assertEqual(action['type'], 'ir.actions.client')
        self.assertEqual(action['tag'], 'wof_setup_flow')

    def test_activities_toggle_add_rename(self):
        general = next(a for a in self.snap['activities'] if a['type'] == 'general')
        self.apply('activity', {'id': general['id'], 'selected': True})
        self.apply('activity_add', {'name': 'التلميع'})
        custom = next(a for a in self.snap['activities'] if a['name'] == 'التلميع')
        self.assertTrue(custom['selected'])
        self.assertFalse(custom['is_default'])
        self.apply('activity', {'id': custom['id'], 'name': 'تلميع احترافي'})
        self.assertIn('تلميع احترافي', [a['name'] for a in self.snap['activities']])
        with self.assertRaises(ValidationError):
            self.apply('activity_add', {'name': 'تلميع احترافي'})

    def test_sizes_add_with_and_without_code(self):
        self.apply('size_add', {'name': 'فان', 'code': 'van'})
        self.assertIn('VAN', [s['code'] for s in self.snap['sizes']])
        self.apply('size_add', {'name': 'شاحنة'})
        self.assertTrue(any(s['code'].startswith('CUSTOM_') for s in self.snap['sizes']))
        with self.assertRaises(ValidationError):
            self.apply('size_add', {'name': 'مكرر', 'code': 'VAN'})
        small = next(s for s in self.snap['sizes'] if s['code'] == 'SMALL')
        self.apply('size', {'id': small['id'], 'selected': False})
        self.assertFalse(next(s for s in self.snap['sizes'] if s['code'] == 'SMALL')['selected'])

    def test_tint_method_and_shades(self):
        self.apply('tint_method', {'method': 'percentage'})
        self.assertEqual([s['value'] for s in self.snap['tint']['shades']], ['00', '30', '50', '75', '100'])
        shade = self.snap['tint']['shades'][0]
        self.apply('shade', {'id': shade['id'], 'selected': False})
        self.assertFalse(self.snap['tint']['shades'][0]['selected'])

    def test_field_states_and_technician_flag(self):
        fields_by_key = {f['key']: f for f in self.snap['fields']}
        self.apply('field', {'id': fields_by_key['vin']['id'], 'state': 'hid'})
        line = self.profile.operation_field_line_ids.filtered(lambda l: l.field_key == 'vin')
        self.assertTrue(line.hidden)
        self.assertFalse(line.required)
        self.apply('field', {'id': fields_by_key['technician']['id'], 'state': 'opt'})
        self.assertFalse(self.profile.operation_technician_required)
        self.apply('field', {'id': fields_by_key['technician']['id'], 'state': 'req'})
        self.assertTrue(self.profile.operation_technician_required)

    def test_invoice_modes(self):
        self.apply('invoice', {'mode': 'after'})
        self.assertEqual(self.snap['invoice'], 'after')
        self.assertEqual(self.profile.payment_policy, 'full_before_invoice')
        self.apply('invoice', {'mode': 'auto'})
        self.assertEqual(self.snap['invoice'], 'auto')
        self.assertEqual(self.profile.payment_policy, 'partial')
        self.apply('invoice', {'mode': 'manual'})
        self.assertEqual(self.snap['invoice'], 'manual')
        self.assertFalse(self.profile.operation_auto_invoice)

    def test_scalar_validation(self):
        self.apply('set', {'discount_enabled': True, 'discount_default_limit': 12, 'discount_scope': 'service'})
        self.assertEqual(self.snap['discount']['limit'], 12)
        self.assertEqual(self.snap['discount']['scope'], 'service')
        with self.assertRaises(ValidationError):
            self.apply('set', {'discount_default_limit': 150})
        with self.assertRaises(ValidationError):
            self.apply('set', {'state': 'ready'})
        with self.assertRaises(ValidationError):
            self.apply('set', {'operation_pricing_policy': 'other'})

    def test_activate_then_tint_method_locked(self):
        self.apply('set', {'operation_tax_enabled': False})
        self.apply('goto', {'step': 'review'})
        self.assertFalse(self.snap['issues'])
        self.apply('activate')
        self.assertEqual(self.snap['state'], 'ready')
        self.assertTrue(self.snap['tint']['locked'])
        sizes = self.env['wof.car.size'].search([])
        self.assertLessEqual({'SMALL', 'MEDIUM', 'LARGE', 'SUV'}, set(sizes.mapped('code')))
        with self.assertRaises(ValidationError):
            self.apply('tint_method', {'method': 'percentage'})

    def test_activation_blocked_by_missing_tax(self):
        self.apply('set', {'operation_tax_enabled': True, 'operation_tax_id': False})
        self.assertIn('SETUP_OPERATION_TAX_REQUIRED', [i['code'] for i in self.snap['issues']])
        with self.assertRaises(ValidationError):
            self.apply('activate')

    def test_requires_setup_group(self):
        manager = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'مدير بدون تهيئة', 'login': 'wof_setup_flow_manager',
            'company_id': self.company.id, 'company_ids': [(6, 0, [self.company.id])],
            'groups_id': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('yousentech_wo_v4.group_wo_manager').id,
            ])],
        })
        with self.assertRaises(AccessError):
            self.profile.with_user(manager).wof_flow_apply('set', {'discount_enabled': True})
