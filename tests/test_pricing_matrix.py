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
        tpl = area['templates'][0]
        self.assertTrue(tpl['is_default'])
        self.assertEqual({child['part_id'] for child in tpl['parts']}, {self.side_a.id, self.side_b.id})
        # Not sold alone in this film: their commission inside the area is the area's own.
        self.assertEqual({child['commission']['method'] for child in tpl['parts']}, {'fixed'})

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

    def test_same_price_for_all_sizes_survives_reload_and_resave(self):
        snap = self.film.wof_matrix_load()
        front = self._line(snap, self.front_line)
        front['price'] = {'mode': 'uniform', 'general': {'amount': 480, 'readonly': False}, 'sizes': {}}
        snap = self.film.wof_matrix_save({'lines': [front]})
        front = self._line(snap, self.front_line)
        # Reported bug: the shared value came back empty, and the next save erased it.
        self.assertEqual(front['price']['mode'], 'uniform')
        self.assertEqual(front['price']['general']['amount'], 480)
        snap = self.film.wof_matrix_save({'lines': [front]})
        self.assertEqual(set(self.front_line.price_line_ids.mapped('part_price')), {480})
        self.assertEqual(len(self.front_line.price_line_ids), 2)

    def test_snapshot_hides_lines_of_the_other_policy(self):
        Price = self.env['wof.film.parts.price.lines']
        # Older data: a general line and per-size lines on the same component.
        Price.create({'part_line_id': self.front_line.id, 'part_price': 111})
        Price.create({'part_line_id': self.front_line.id, 'car_size_id': self.small.id, 'part_price': 222})
        Price.create({'part_line_id': self.front_line.id, 'car_size_id': self.large.id, 'part_price': 333})
        front = self._line(self.film.wof_matrix_load(), self.front_line)
        self.assertEqual(front['price']['mode'], 'size')
        self.assertIsNone(front['price']['general']['amount'])
        self.film.pricing_policy = 'fixed'
        front = self._line(self.film.wof_matrix_load(), self.front_line)
        self.assertEqual(front['price']['general']['amount'], 111)
        self.assertTrue(all(cell['amount'] is None for cell in front['price']['sizes'].values()))
        self.film.wof_matrix_save({'lines': [front]})
        self.assertEqual(self.front_line.price_line_ids.mapped('part_price'), [111])

    def _area_part(self, snap, part, template=None):
        area = self._line(snap, self.area_line)
        tpl = next(t for t in area['templates'] if (t['id'] == template.id if template else t['is_default']))
        return area, next(child for child in tpl['parts'] if child['part_id'] == part.id)

    def test_area_commission_derived_from_default_template_parts(self):
        snap = self.film.wof_matrix_load()
        area, side_a = self._area_part(snap, self.side_a)
        _area, side_b = self._area_part(snap, self.side_b)
        area['commission'].update({'source': 'from_parts'})
        side_a['commission'].update({'method': 'by_size', 'sizes': {str(self.small.id): 20, str(self.large.id): 30}})
        side_b['commission'].update({'method': 'fixed', 'general': 25})
        self.film.wof_matrix_save({'lines': [area]})

        self.assertEqual(self.area_line.service_commission_source, 'from_parts')
        self.assertEqual(self.area_line.technician_commission_distribution, 'by_part')
        derived = {line.car_size_id.id: line.commission for line in self.area_line.commission_line_ids}
        self.assertEqual(derived, {self.small.id: 45, self.large.id: 55})
        # No film line is created for the parts: their setting belongs to the area.
        self.assertFalse(self.film.film_part_line_ids.filtered(lambda l: l.car_part_id in (self.side_a | self.side_b)))
        self.assertTrue(self.film._wof_readiness()['lines'][self.area_line.id]['commission'])

    def _sell_alone(self, part, commission):
        """Sell ``part`` alone in the film with ``commission`` (matrix snapshot dict update)."""
        line = self.env['wof.film.parts.lines'].create({'header_id': self.film.id, 'car_part_id': part.id, 'sequence': 5})
        snap = self.film.wof_matrix_load()
        item = self._line(snap, line)
        item['price'] = {'mode': 'size', 'general': {'amount': None}, 'sizes': {
            str(self.small.id): {'amount': 200}, str(self.large.id): {'amount': 300}}}
        item['commission'].update(commission)
        self.film.wof_matrix_save({'lines': [item]})
        return line

    def test_part_inside_area_follows_or_leaves_the_part_sold_alone(self):
        alone = self._sell_alone(self.side_a, {'type': 'percent', 'policy': 'fixed', 'general': 10,
                                               'distribution': 'by_technician_ratio'})
        snap = self.film.wof_matrix_load()
        area, side_a = self._area_part(snap, self.side_a)
        _area, side_b = self._area_part(snap, self.side_b)
        # Sold alone: «حسب تهيئة الجزء» by default, a percentage becomes an amount of its price.
        self.assertTrue(side_a['standalone'])
        self.assertEqual(side_a['commission']['method'], 'part')
        self.assertEqual(side_a['commission']['distribution'], 'part')
        self.assertEqual(side_a['resolved'], {str(self.small.id): 20.0, str(self.large.id): 30.0})
        area['commission'].update({'source': 'from_parts'})
        side_b['commission'].update({'method': 'fixed', 'general': 5})
        self.film.wof_matrix_save({'lines': [area]})
        derived = {line.car_size_id.id: line.commission for line in self.area_line.commission_line_ids}
        self.assertEqual(derived, {self.small.id: 25.0, self.large.id: 35.0})
        film = self.film
        template = self.area.default_template_id
        self.assertEqual(film._wof_area_part_rule(self.area_line, template, self.side_a), 'by_technician_ratio')

        # Its own value inside the area does not touch the part sold alone.
        snap = film.wof_matrix_load()
        area, side_a = self._area_part(snap, self.side_a)
        side_a['commission'].update({'method': 'fixed', 'general': 7, 'distribution': 'equal'})
        film.wof_matrix_save({'lines': [area]})
        self.assertEqual(alone.commission_value_type, 'percent')
        self.assertEqual(alone.commission_line_ids.mapped('commission'), [10.0])
        self.assertEqual(alone.technician_commission_distribution, 'by_technician_ratio')
        self.assertEqual(film._wof_area_part_value(self.area_line, template, self.side_a, self.small), 7.0)
        self.assertEqual(film._wof_area_part_rule(self.area_line, template, self.side_a), 'equal')

        # And the part sold alone changing does not touch that value.
        snap = film.wof_matrix_load()
        item = self._line(snap, alone)
        item['commission'].update({'general': 50})
        film.wof_matrix_save({'lines': [item]})
        self.assertEqual(film._wof_area_part_value(self.area_line, template, self.side_a, self.small), 7.0)

    def test_part_not_sold_alone_cannot_follow_it(self):
        snap = self.film.wof_matrix_load()
        area, side_a = self._area_part(snap, self.side_a)
        self.assertFalse(side_a['standalone'])
        side_a['commission'].update({'method': 'part'})
        with self.assertRaises(ValidationError):
            self.film.wof_matrix_save({'lines': [area]})

    def test_each_template_has_its_parts_and_orders_use_theirs(self):
        extra = self.env['wof.car.parts'].create({
            'code': 'PM-SC', 'name': 'جانبي ج PM', 'part_type': 'car_part',
            'product_id': self.env['product.product'].create({'name': 'ج', 'type': 'service'}).id})
        big = self.env['wof.service.area.template'].create({
            'name': 'النموذج الكبير', 'service_area_id': self.area.id,
            'component_ids': [(6, 0, (self.side_a | self.side_b | extra).ids)]})
        snap = self.film.wof_matrix_load()
        area = self._line(snap, self.area_line)
        self.assertEqual([tpl['name'] for tpl in area['templates']], ['النموذج الأساسي', 'النموذج الكبير'])
        area['commission'].update({'source': 'from_parts'})
        for tpl in area['templates']:
            for child in tpl['parts']:
                child['commission'].update({'method': 'fixed', 'general': 10})
        self.film.wof_matrix_save({'lines': [area]})
        self.assertEqual(self.film._wof_area_total(self.area_line, self.area.default_template_id, self.small), 20.0)
        self.assertEqual(self.film._wof_area_total(self.area_line, big, self.small), 30.0)
        # A missing part in any template keeps the area incomplete.
        snap = self.film.wof_matrix_load()
        area = self._line(snap, self.area_line)
        area['templates'][1]['parts'][2]['commission'].update({'general': None})
        self.film.wof_matrix_save({'lines': [area]})
        self.assertFalse(self.film._wof_readiness()['lines'][self.area_line.id]['commission'])

    def test_foreign_template_is_rejected(self):
        other_area = self.env['wof.car.parts'].create({
            'code': 'PM-AREA2', 'name': 'منطقة أخرى PM', 'part_type': 'service_area',
            'product_id': self.env['product.product'].create({'name': 'م', 'type': 'service'}).id})
        foreign = self.env['wof.service.area.template'].create({
            'name': 'نموذج غريب', 'service_area_id': other_area.id, 'component_ids': [(6, 0, self.side_a.ids)]})
        snap = self.film.wof_matrix_load()
        area = self._line(snap, self.area_line)
        area['templates'][0]['id'] = foreign.id
        with self.assertRaises(ValidationError):
            self.film.wof_matrix_save({'lines': [area]})

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
