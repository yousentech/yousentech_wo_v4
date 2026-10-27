# -*- coding: utf-8 -*-
"""Runtime tests for the films & services page and the guided film editor.

Run on a test database:
    odoo-bin -d <db> -u yousentech_wo_v4 --test-enable --test-tags /yousentech_wo_v4:TestFilmsFlow --stop-after-init
"""

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestFilmsFlow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.company = env['res.company'].create({'name': 'شركة اختبار الأفلام'})
        cls.user = env['res.users'].with_context(no_reset_password=True).create({
            'name': 'مدير أفلام الاختبار', 'login': 'wof_films_flow_tester',
            'company_id': cls.company.id, 'company_ids': [(6, 0, [cls.company.id])],
            'groups_id': [(6, 0, [
                env.ref('base.group_user').id,
                env.ref('yousentech_wo_v4.group_wo_settings').id,
            ])],
        })
        uenv = env(user=cls.user, context=dict(env.context, allowed_company_ids=[cls.company.id]))
        profile = uenv['wof.company.profile'].get_or_create_for_company(cls.company)
        profile.wof_flow_load()
        profile.wof_flow_apply('set', {'operation_tax_enabled': False})
        profile.wof_flow_apply('activate')
        cls.uenv = uenv
        cls.Film = uenv['wof.film.category']
        cls.activity = uenv['wof.service.type'].search([
            ('company_id', '=', cls.company.id), ('service_options', '=', 'tint'),
        ], limit=1)

        def part(code, name, part_type='car_part', kids=None):
            product = env['product.product'].create({'name': name, 'type': 'service', 'company_id': cls.company.id})
            vals = {'code': code, 'name': name, 'part_type': part_type,
                    'company_id': cls.company.id, 'product_id': product.id}
            record = env['wof.car.parts'].create(vals)
            if kids:
                env['wof.service.area.template'].create({
                    'name': 'النموذج الأساسي', 'service_area_id': record.id,
                    'component_ids': [(6, 0, kids.ids)], 'is_default': True,
                })
            return record

        cls.front = part('FF-FRONT', 'أمامي FF')
        cls.rear = part('FF-REAR', 'خلفي FF')
        cls.empty_area = part('FF-EMPTY', 'منطقة فارغة FF', 'service_area')
        cls.area = part('FF-AREA', 'منطقة FF', 'service_area', kids=cls.front | cls.rear)

    def new_film(self, name='فيلم المحرر'):
        return self.Film.browse(self.Film.wof_film_create(self.activity.id, name, 'film'))

    def price_all(self, film):
        snap = film.wof_matrix_load()
        for line in snap['lines']:
            line['price'] = {'mode': 'uniform', 'general': {'amount': 500, 'readonly': False}, 'sizes': {}}
        film.wof_matrix_save({'lines': snap['lines']})

    def test_create_blank_film_is_inactive_with_system_grades(self):
        film = self.new_film()
        self.assertFalse(film.active)
        self.assertEqual(len(film.film_category_line_ids.filtered('active')), 5)
        self.assertTrue(film.use_system_tint_grades)
        self.assertEqual((film.warranty_period, film.warranty_unit, film.warranty_years), (1, 'year', 1))
        action = film.action_configure()
        self.assertEqual(action['tag'], 'wof_film_editor')

    def test_warranty_units_keep_legacy_years(self):
        film = self.new_film()
        film.wof_film_apply('basic', {'warranty_period': 6, 'warranty_unit': 'month'})
        self.assertEqual(film.warranty_years, 0)
        film.wof_film_apply('basic', {'warranty_period': 24})
        self.assertEqual(film.warranty_years, 2)
        film.write({'warranty_years': 3})
        self.assertEqual((film.warranty_period, film.warranty_unit), (3, 'year'))
        with self.assertRaises(ValidationError):
            film.wof_film_apply('basic', {'warranty_unit': 'week'})
        with self.assertRaises(ValidationError):
            film.wof_film_apply('basic', {'active': True})

    def test_components_add_move_remove(self):
        film = self.new_film()
        film.wof_film_apply('comp_add', {'part_id': self.front.id})
        snap = film.wof_film_apply('comp_add', {'part_id': self.area.id})
        self.assertEqual([c['part_id'] for c in snap['components']], [self.front.id, self.area.id])
        self.assertEqual(len(snap['components'][1]['kids']), 2)
        area_line = snap['components'][1]['line_id']
        snap = film.wof_film_apply('comp_move', {'line_id': area_line, 'direction': 'up'})
        self.assertEqual(snap['components'][0]['part_id'], self.area.id)
        snap = film.wof_film_apply('comp_remove', {'line_id': area_line})
        self.assertEqual([c['part_id'] for c in snap['components']], [self.front.id])
        self.assertTrue(film.film_part_line_ids.filtered(lambda l: l.car_part_id == self.area))
        with self.assertRaises(ValidationError):
            film.wof_film_apply('comp_add', {'part_id': self.empty_area.id})
        self.assertNotIn(self.front.id, [p['id'] for p in film.wof_film_parts_search('FF')])

    def test_specific_tint_archives_and_all_restores(self):
        film = self.new_film()
        snap = film.wof_film_apply('tint', {'use_all': False, 'code': 'SEQ-04', 'selected': False})
        self.assertFalse(snap['tint']['use_all'])
        self.assertEqual(len(snap['grades']), 4)
        archived = film.with_context(active_test=False).film_category_line_ids.filtered(lambda g: not g.active)
        self.assertEqual(archived.mapped('code'), ['SEQ-04'])
        snap = film.wof_film_apply('tint', {'use_all': True})
        self.assertEqual(len(snap['grades']), 5)

    def test_component_tint_policy(self):
        film = self.new_film()
        snap = film.wof_film_apply('comp_add', {'part_id': self.front.id})
        grades = snap['grades']
        line_id = snap['components'][0]['line_id']
        snap = film.wof_film_apply('comp_tint', {
            'line_id': line_id, 'default_grade_id': grades[2]['id'], 'allowed_ids': [grades[1]['id']],
        })
        comp = snap['components'][0]
        self.assertEqual(comp['default_grade_id'], grades[2]['id'])
        self.assertEqual(set(comp['allowed_ids']), {grades[1]['id'], grades[2]['id']})

    def test_policy_custom_and_inherit(self):
        film = self.new_film()
        snap = film.wof_film_apply('policy', {'key': 'pricing', 'custom': True, 'value': 'by_size'})
        self.assertTrue(snap['policies']['pricing']['custom'])
        self.assertEqual(film.pricing_policy, 'by_size')
        snap = film.wof_film_apply('policy', {'key': 'pricing', 'custom': False})
        self.assertFalse(snap['policies']['pricing']['custom'])
        self.assertEqual(film.pricing_policy, snap['policies']['pricing']['system'])
        film.wof_film_apply('policy', {'key': 'discount', 'custom': True, 'enabled': True, 'limit': 7})
        self.assertEqual((film.use_system_discount_policy, film.discount_limit), (False, 7))
        with self.assertRaises(ValidationError):
            film.wof_film_apply('policy', {'key': 'discount', 'custom': True, 'enabled': True, 'limit': 120})

    def test_activation_requires_prices(self):
        film = self.new_film()
        film.wof_film_apply('comp_add', {'part_id': self.front.id})
        with self.assertRaises(ValidationError):
            film.wof_film_apply('activate')
        self.price_all(film)
        snap = film.wof_film_apply('activate')
        self.assertTrue(snap['film']['active'])
        self.assertTrue(snap['readiness']['ready'])

    def test_zero_price_is_not_a_price_unless_free(self):
        film = self.new_film()
        film.wof_film_apply('comp_add', {'part_id': self.front.id})
        snap = film.wof_matrix_load()
        for line in snap['lines']:
            line['price'] = {'mode': 'uniform', 'general': {'amount': 0, 'readonly': False}, 'sizes': {}}
        film.wof_matrix_save({'lines': snap['lines']})
        self.assertFalse(film._wof_readiness()['ready'])
        with self.assertRaises(ValidationError):
            film.wof_film_apply('activate')
        for line in snap['lines']:
            line['price'] = {'mode': 'free', 'general': {'amount': 0, 'free': True, 'readonly': False}, 'sizes': {}}
        film.wof_matrix_save({'lines': snap['lines']})
        self.assertTrue(film._wof_readiness()['ready'])

    def test_copy_with_components_prices_and_grades(self):
        source = self.new_film('فيلم المصدر')
        snap = source.wof_film_apply('comp_add', {'part_id': self.front.id})
        source.wof_film_apply('comp_tint', {'line_id': snap['components'][0]['line_id'],
                                            'default_grade_id': snap['grades'][1]['id'], 'allowed_ids': []})
        self.price_all(source)
        copy = self.Film.browse(self.Film.wof_film_copy(source.id, self.activity.id, 'فيلم منسوخ', {
            'components': True, 'tint': True, 'policies': True, 'prices': True, 'commissions': False,
        }))
        self.assertFalse(copy.active)
        self.assertNotEqual(copy.code, source.code)
        line = copy.film_part_line_ids
        self.assertEqual(line.car_part_id, self.front)
        self.assertEqual(line.film_category_line_id.header_id, copy)
        self.assertEqual(line.film_category_line_id.code, snap['grades'][1]['code'])
        self.assertEqual(line.price_line_ids.mapped('part_price'), [500])
        self.assertTrue(copy._wof_readiness()['ready'])

    def test_hub_load_and_access(self):
        film = self.new_film('فيلم البوابة')
        data = self.Film.wof_films_hub_load()
        card = next(c for c in data['films'] if c['id'] == film.id)
        self.assertFalse(card['ready'])
        self.assertIn('components', card['missing'])
        employee = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'موظف', 'login': 'wof_films_flow_employee',
            'company_id': self.company.id, 'company_ids': [(6, 0, [self.company.id])],
            'groups_id': [(6, 0, [self.env.ref('yousentech_wo_v4.group_wo_employee').id])],
        })
        with self.assertRaises(AccessError):
            self.Film.with_user(employee).wof_films_hub_load()

    def test_legacy_grade_codes_match_by_name(self):
        film = self.new_film('فيلم بأكواد قديمة')
        for grade in film.film_category_line_ids:
            grade.code = 'OLD-' + grade.name
        snap = film.wof_film_load()
        self.assertTrue(all(shade['selected'] for shade in snap['tint']['shades']))
        snap = film.wof_film_apply('tint', {'use_all': False})
        self.assertFalse(snap['tint']['use_all'])
        self.assertEqual(sum(shade['selected'] for shade in snap['tint']['shades']), 5)
        snap = film.wof_film_apply('tint', {'use_all': False, 'code': 'SEQ-00', 'selected': False})
        self.assertEqual(sum(shade['selected'] for shade in snap['tint']['shades']), 4)

    def test_bulk_add_and_component_master(self):
        film = self.new_film('فيلم المكوّنات')
        snap = film.wof_film_apply('comp_add_many', {'part_ids': [self.front.id, self.area.id]})
        self.assertEqual(len(snap['components']), 2)
        area = next(c for c in snap['components'] if c['type'] == 'service_area')
        self.assertEqual(area['templates'][0]['is_default'], True)
        with self.assertRaises(ValidationError):
            film.wof_film_apply('comp_add_many', {'part_ids': [self.front.id]})
        with self.assertRaises(ValidationError):
            film.wof_film_apply('comp_add_many', {'part_ids': [self.empty_area.id]})
        self.assertEqual({p['type'] for p in film.wof_film_parts_search('', 'car_part')}, {'car_part'})

        # new car part, auto code and auto product, added to the film
        snap = film.wof_component_save({'type': 'car_part', 'name': 'سقف FF', 'auto_product': True,
                                        'priority': 5, 'warning_msg': 'انتبه'})
        roof = self.uenv['wof.car.parts'].search([('name', '=', 'سقف FF'), ('company_id', '=', self.company.id)])
        self.assertTrue(roof.code.startswith('PART-'))
        self.assertEqual(roof.product_id.type, 'service')
        self.assertIn(roof.id, [c['part_id'] for c in snap['components']])
        with self.assertRaises(ValidationError):
            film.wof_component_save({'type': 'car_part', 'name': 'سقف FF', 'auto_product': True})

        # new service area with two templates; default drives the legacy part list
        film.wof_component_save({'type': 'service_area', 'name': 'منطقة جديدة FF', 'auto_product': True, 'templates': [
            {'name': 'كامل', 'is_default': False, 'component_ids': [self.front.id, self.rear.id]},
            {'name': 'أمامي فقط', 'is_default': True, 'component_ids': [self.front.id]},
        ]})
        new_area = self.uenv['wof.car.parts'].search([('name', '=', 'منطقة جديدة FF')])
        self.assertEqual(new_area.default_template_id.name, 'أمامي فقط')
        self.assertEqual(new_area.service_area_part_ids, self.front)
        with self.assertRaises(ValidationError):
            film.wof_component_save({'type': 'service_area', 'name': 'منطقة خطأ FF', 'auto_product': True, 'templates': [
                {'name': 'أ', 'is_default': True, 'component_ids': []}]})

        # edit: switch the default template and drop one
        info = film.wof_component_load(new_area.id)
        templates = info['part']['templates']
        film.wof_component_save({'id': new_area.id, 'name': new_area.name, 'auto_product': False,
                                 'product_id': new_area.product_id.id, 'templates': [
            dict(templates[0], is_default=False), dict(templates[1], is_default=True),
        ] if templates[0]['is_default'] else [dict(templates[1], is_default=False), dict(templates[0], is_default=True)]})
        self.assertEqual(new_area.default_template_id.name, 'كامل')

    def test_drag_reorder(self):
        film = self.new_film('فيلم الترتيب')
        snap = film.wof_film_apply('comp_add_many', {'part_ids': [self.front.id, self.rear.id, self.area.id]})
        ids = [c['line_id'] for c in snap['components']]
        snap = film.wof_film_apply('comp_reorder', {'line_ids': [ids[2], ids[0], ids[1]]})
        self.assertEqual([c['line_id'] for c in snap['components']], [ids[2], ids[0], ids[1]])
        with self.assertRaises(ValidationError):
            film.wof_film_apply('comp_reorder', {'line_ids': ids[:2]})
