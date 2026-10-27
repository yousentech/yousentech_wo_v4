# -*- coding: utf-8 -*-
"""Runtime tests for the pricing & commission matrix service.

Run on a test database:
    odoo-bin -d <db> -u yousentech_wo_v4 --test-enable --test-tags /yousentech_wo_v4:TestPricingMatrix --stop-after-init
"""

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPricingMatrix(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.small = env['wof.car.size'].create({'code': 'PMS', 'name': 'صغير PM'})
        cls.large = env['wof.car.size'].create({'code': 'PML', 'name': 'كبير PM'})
        cls.activity = env['wof.service.type'].create({
            'code': 'PM-ACT', 'name': 'نشاط اختبار المصفوفة', 'service_options': 'ppf',
        })

        def product(name):
            return env['product.product'].create({'name': name, 'type': 'service'})

        def part(code, name, part_type='car_part'):
            return env['wof.car.parts'].create({
                'code': code, 'name': name, 'part_type': part_type,
                'product_id': product(name).id,
            })

        cls.front = part('PM-FRONT', 'أمامي PM')
        cls.side_a = part('PM-SA', 'جانبي أ PM')
        cls.side_b = part('PM-SB', 'جانبي ب PM')
        cls.area = part('PM-AREA', 'منطقة PM', 'service_area')
        env['wof.service.area.template'].create({
            'name': 'النموذج الأساسي', 'service_area_id': cls.area.id,
            'component_ids': [(6, 0, (cls.side_a | cls.side_b).ids)], 'is_default': True,
        })
        cls.film = env['wof.film.category'].create({
            'name': 'فيلم المصفوفة', 'code': 'PM-FILM', 'service_type_id': cls.activity.id,
            'pricing_policy': 'by_size', 'commission_calculation_policy': 'fixed',
            'car_size_ids': [(6, 0, (cls.small | cls.large).ids)], 'tax_enabled': False,
        })
        Line = env['wof.film.parts.lines']
        cls.front_line = Line.create({'header_id': cls.film.id, 'car_part_id': cls.front.id, 'sequence': 10})
        cls.area_line = Line.create({'header_id': cls.film.id, 'car_part_id': cls.area.id, 'sequence': 20})

    def _line(self, snapshot, line):
        return next(item for item in snapshot['lines'] if item['id'] == line.id)

    def test_load_snapshot_lists_commercial_lines_and_template_parts(self):
        snap = self.film.wof_matrix_load()
        self.assertEqual([line['id'] for line in snap['lines']], [self.front_line.id, self.area_line.id])
        self.assertEqual(len(snap['sizes']), 2)
        area = self._line(snap, self.area_line)
        self.assertEqual(area['template_name'], 'النموذج الأساسي')
        self.assertEqual({child['part_id'] for child in area['children']}, {self.side_a.id, self.side_b.id})

    def test_save_per_size_uniform_and_free_prices(self):
        snap = self.film.wof_matrix_load()
        front = self._line(snap, self.front_line)
        front['price'] = {'mode': 'size', 'general': {}, 'sizes': {
            str(self.small.id): {'amount': 300, 'free': False, 'readonly': True},
            str(self.large.id): {'amount': None, 'free': True, 'readonly': False},
        }}
        area = self._line(snap, self.area_line)
        area['price'] = {'mode': 'uniform', 'general': {'amount': 1000, 'readonly': True}, 'sizes': {}}
        self.film.wof_matrix_save({'lines': [front, area]})

        small_line = self.front_line.price_line_ids.filtered(lambda l: l.car_size_id == self.small)
        large_line = self.front_line.price_line_ids.filtered(lambda l: l.car_size_id == self.large)
        self.assertEqual(small_line.part_price, 300)
        self.assertTrue(small_line.price_readonly)
        self.assertTrue(large_line.free_part)
        self.assertEqual(large_line.part_price, 0)
        self.assertEqual(len(self.area_line.price_line_ids), 2)
        self.assertEqual(set(self.area_line.price_line_ids.mapped('part_price')), {1000})
        self.assertFalse(self.area_line.price_line_ids.filtered(lambda l: not l.car_size_id))

    def test_switch_to_fixed_policy_writes_one_general_line(self):
        snap = self.film.wof_matrix_load()
        front = self._line(snap, self.front_line)
        front['price'] = {'mode': 'uniform', 'general': {'amount': 250, 'readonly': False}, 'sizes': {}}
        self.film.wof_matrix_save({'pricing_policy': 'fixed', 'lines': [front]})
        self.assertEqual(self.film.pricing_policy, 'fixed')
        self.assertFalse(self.film.use_system_pricing_policy)
        self.assertEqual(len(self.front_line.price_line_ids), 1)
        self.assertFalse(self.front_line.price_line_ids.car_size_id)
        self.assertEqual(self.front_line.price_line_ids.part_price, 250)

    def test_area_commission_derived_from_default_template_parts(self):
        snap = self.film.wof_matrix_load()
        area = self._line(snap, self.area_line)
        area['commission'].update({'source': 'from_parts'})
        for child in area['children']:
            if child['part_id'] == self.side_a.id:
                child['commission'].update({'policy': 'by_size', 'sizes': {str(self.small.id): 20, str(self.large.id): 30}})
            else:
                child['commission'].update({'policy': 'fixed', 'general': 25})
        self.film.wof_matrix_save({'lines': [area]})

        self.assertEqual(self.area_line.service_commission_source, 'from_parts')
        self.assertEqual(self.area_line.technician_commission_distribution, 'by_part')
        derived = {line.car_size_id.id: line.commission for line in self.area_line.commission_line_ids}
        self.assertEqual(derived, {self.small.id: 45, self.large.id: 55})
        basis = self.film.film_part_line_ids.filtered(lambda l: l.car_part_id in (self.side_a | self.side_b))
        self.assertEqual(len(basis), 2)
        self.assertFalse(any(basis.mapped('part_selected')))

    def test_commission_validation(self):
        snap = self.film.wof_matrix_load()
        front = self._line(snap, self.front_line)
        front['commission'].update({'type': 'percent', 'policy': 'fixed', 'general': 150})
        with self.assertRaises(ValidationError):
            self.film.wof_matrix_save({'lines': [front]})
        front['commission'].update({'type': 'fixed', 'general': -5})
        with self.assertRaises(ValidationError):
            self.film.wof_matrix_save({'lines': [front]})

    def test_foreign_line_is_rejected(self):
        other = self.film.copy({'name': 'فيلم آخر PM', 'code': 'PM-OTHER'})
        snap = self.film.wof_matrix_load()
        front = self._line(snap, self.front_line)
        with self.assertRaises(ValidationError):
            other.wof_matrix_save({'lines': [front]})
