# -*- coding: utf-8 -*-
"""Settings and installation orders are shared by every branch.

Run on a test database:
    odoo-bin -d <db> -u yousentech_wo_v4 --test-enable --test-tags /yousentech_wo_v4:TestSharedBranches --stop-after-init
"""

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSharedBranches(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.main = env['res.company'].create({'name': 'الفرع الرئيسي للاختبار'})
        cls.branch = env['res.company'].create({'name': 'فرع جدة للاختبار', 'parent_id': cls.main.id})

        def user(login, company, groups):
            return env['res.users'].with_context(no_reset_password=True).create({
                'name': login, 'login': login,
                'company_id': company.id, 'company_ids': [(6, 0, [company.id])],
                'groups_id': [(6, 0, [env.ref('base.group_user').id] + [env.ref(g).id for g in groups])],
            })

        settings = ['yousentech_wo_v4.group_wo_settings', 'yousentech_wo_v4.group_wo_supervisor']
        cls.main_user = user('wof_shared_main', cls.main, settings)
        cls.branch_user = user('wof_shared_branch', cls.branch, settings)
        cls.main_env = env(user=cls.main_user, context=dict(env.context, allowed_company_ids=[cls.main.id]))
        cls.branch_env = env(user=cls.branch_user, context=dict(env.context, allowed_company_ids=[cls.branch.id]))

        profile = cls.main_env['wof.company.profile'].get_or_create_for_company()
        profile.wof_flow_load()
        profile.wof_flow_apply('set', {'operation_tax_enabled': False})
        profile.wof_flow_apply('activate')
        cls.profile = profile

        Film = cls.main_env['wof.film.category']
        cls.activity = cls.main_env['wof.service.type'].search([('service_options', '=', 'tint'), ('active', '=', True)], limit=1)
        product = env['product.product'].create({'name': 'زجاج مشترك', 'type': 'service'})
        cls.part = env['wof.car.parts'].create({
            'code': 'SH-FRONT', 'name': 'زجاج أمامي مشترك', 'part_type': 'car_part', 'product_id': product.id,
        })
        cls.film = Film.browse(Film.wof_film_create(cls.activity.id, 'فيلم مشترك', 'film'))
        cls.film.wof_film_apply('comp_add', {'part_id': cls.part.id})
        snap = cls.film.wof_matrix_load()
        for line in snap['lines']:
            line['price'] = {'mode': 'uniform', 'general': {'amount': 400, 'readonly': False}, 'sizes': {}}
        cls.film.wof_matrix_save({'lines': snap['lines']})
        cls.film.wof_film_apply('activate')

    def test_one_setup_for_all_branches(self):
        branch_profile = self.branch_env['wof.company.profile'].get_or_create_for_company()
        self.assertEqual(branch_profile, self.profile.with_env(self.branch_env))
        self.assertEqual(self.env['wof.company.profile'].search_count([]), 1)
        self.assertEqual(branch_profile.state, 'ready')

    def test_branch_sees_and_edits_settings_of_main(self):
        Film = self.branch_env['wof.film.category']
        hub = Film.wof_films_hub_load()
        self.assertIn(self.film.id, [card['id'] for card in hub['films']])
        film = Film.browse(self.film.id)
        # Previously: "لا يمكنك تعديل فيلم أو خدمة لشركة غير مسموحة."
        snap = film.wof_film_apply('basic', {'description': 'عدّله فرع جدة'})
        self.assertEqual(snap['film']['id'], self.film.id)
        matrix = film.wof_matrix_load()
        self.assertEqual(len(matrix['lines']), 1)
        film.wof_matrix_save({'lines': matrix['lines']})
        sizes = self.branch_env['wof.car.size'].search([])
        self.assertTrue(sizes)

    def test_branch_creates_settings_visible_to_main(self):
        Film = self.branch_env['wof.film.category']
        film_id = Film.wof_film_create(self.activity.id, 'فيلم من الفرع', 'film')
        self.assertIn(film_id, [card['id'] for card in self.main_env['wof.film.category'].wof_films_hub_load()['films']])

    def test_orders_shared_but_owned_by_branch(self):
        partner = self.env['res.partner'].create({'name': 'عميل مشترك', 'mobile': '0500000000'})
        size = self.main_env['wof.car.size'].search([], limit=1)
        order = self.main_env['wof.installation.order'].create({
            'partner_id': partner.id, 'vehicle_plate': 'abc 123', 'car_size_id': size.id,
            'advisor_id': self.main_user.id,
        })
        self.assertEqual(order.company_id, self.main)
        seen = self.branch_env['wof.installation.order'].search([('id', '=', order.id)])
        self.assertEqual(seen.id, order.id)
        self.assertEqual(seen.name, order.name)
        # Staff of other branches can be assigned.
        self.assertIn(self.branch_user, order.advisor_candidate_ids)
