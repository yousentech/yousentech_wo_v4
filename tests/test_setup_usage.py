# -*- coding: utf-8 -*-
"""Master data used by films and orders stays coherent; setup menus open the guided screens."""

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSetupUsage(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        root = cls.root = cls.env
        groups = ['base.group_user', 'yousentech_wo_v4.group_wo_settings', 'yousentech_wo_v4.group_wo_manager']
        cls.user = root['res.users'].with_context(no_reset_password=True).create({
            'name': 'مسؤول تهيئة الحماية', 'login': 'wof_usage_tester', 'email': 'usage@example.com',
            'groups_id': [(6, 0, [root.ref(g).id for g in groups])],
        })
        env = cls.env = root(user=cls.user)
        profile = env['wof.company.profile']._wof_get_profile() or env['wof.company.profile'].get_or_create_for_company()
        profile.wof_flow_load()
        if profile.state != 'ready':
            profile.wof_flow_apply('set', {'operation_tax_enabled': False})
            profile.wof_flow_apply('activate')
        cls.profile = profile
        service = root['product.product'].create({'name': 'خدمة الحماية', 'type': 'service'})
        cls.part = root['wof.car.parts'].create({
            'code': 'USE-PART', 'name': 'جزء الحماية', 'part_type': 'car_part', 'product_id': service.id,
        })
        Film = env['wof.film.category']
        cls.activity = env['wof.service.type'].search([('service_options', '=', 'tint'), ('active', '=', True)], limit=1)
        cls.film = Film.browse(Film.wof_film_create(cls.activity.id, 'فيلم الحماية', 'film'))
        cls.film.wof_film_apply('comp_add', {'part_id': cls.part.id})
        snap = cls.film.wof_matrix_load()
        for line in snap['lines']:
            line['price'] = {'mode': 'uniform', 'general': {'amount': 300, 'readonly': False}, 'sizes': {}}
        cls.film.wof_matrix_save({'lines': snap['lines']})
        cls.film.wof_film_apply('activate')

    def size_line(self, code=None):
        lines = self.profile.size_line_ids.filtered('selected')
        return lines.filtered(lambda line: line.code == code) if code else lines[:1]

    def master_size(self, line):
        return self.env['wof.car.size'].with_context(active_test=False).search([('code', '=', line.code)])

    def make_order(self, size):
        partner = self.root['res.partner'].create({'name': 'عميل الحماية', 'mobile': '0500000077'})
        order = self.env['wof.installation.order'].create({
            'partner_id': partner.id, 'vehicle_plate': 'USE 1', 'car_size_id': size.id,
        })
        self.env['wof.installation.order.line'].create({
            'order_id': order.id, 'service_type_id': self.activity.id,
            'film_category_id': self.film.id, 'car_part_id': self.part.id,
        })
        return order

    def row(self, data, key, line):
        return next(row for row in data[key] if row['id'] == line.id)

    # ------------------------------------------------------------- menus
    def test_setup_center_opens_guided_screen(self):
        action = self.profile.action_open_setup_center()
        self.assertEqual(action['tag'], 'wof_setup_flow')
        menus = self.root['ir.ui.menu'].with_context(**{'ir.ui.menu.full_list': True}).search([('parent_id', '=', self.root.ref('yousentech_wo_v4.menu_wo_v4_configuration').id)])
        names = set(menus.mapped('name'))
        for gone in ('قائمة الأفلام (عرض جدولي)', 'الأسعار المتقدمة', 'العمولات المتقدمة', 'احجام السيارة', 'أنشطة المركز'):
            self.assertNotIn(gone, names)
        self.assertIn('الأفلام والخدمات', names)

    # ------------------------------------------------------------- sizes
    def test_used_size_is_locked(self):
        line = self.size_line()
        size = self.master_size(line)
        data = self.profile.wof_flow_load()
        self.assertTrue(self.row(data, 'sizes', line)['used'])  # priced in the film
        with self.assertRaises(ValidationError):
            self.profile.wof_flow_apply('size', {'id': line.id, 'name': 'اسم جديد'})
        with self.assertRaises(ValidationError):
            size.name = 'اسم جديد'
        with self.assertRaises(ValidationError):
            size.unlink()
        # An open order needs it: it cannot be switched off.
        order = self.make_order(size)
        data = self.profile.wof_flow_load()
        self.assertTrue(self.row(data, 'sizes', line)['off_block'])
        with self.assertRaises(ValidationError):
            self.profile.wof_flow_apply('size', {'id': line.id, 'selected': False})
        # Once the order is closed, stopping archives the master at once (system live).
        order.write({'cancellation_reason': 'اختبار'})
        order.action_cancel()
        self.profile.wof_flow_apply('size', {'id': line.id, 'selected': False})
        self.assertFalse(size.active)
        self.profile.wof_flow_apply('size', {'id': line.id, 'selected': True})
        self.assertTrue(size.active)

    def test_live_changes_reach_master_data(self):
        self.assertEqual(self.profile.state, 'ready')
        self.profile.wof_flow_apply('size_add', {'name': 'فان الحماية', 'code': 'VAN-USE'})
        size = self.env['wof.car.size'].search([('code', '=', 'VAN-USE')])
        self.assertEqual(size.name, 'فان الحماية')
        line = self.size_line('VAN-USE')
        self.profile.wof_flow_apply('size', {'id': line.id, 'name': 'فان كبير'})
        self.assertEqual(size.name, 'فان كبير')
        # The last active size cannot go while the system is live.
        others = self.profile.size_line_ids.filtered('selected') - line
        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                for other in others:
                    self.profile.wof_flow_apply('size', {'id': other.id, 'selected': False})
                self.profile.wof_flow_apply('size', {'id': line.id, 'selected': False})

    # ------------------------------------------------------------ shades
    def test_shade_rename_and_choice_survive_reload(self):
        shade = self.profile.tint_shade_line_ids.filtered('selected')[-1:]
        # Shades of this database may all be used by other tests' films: write past the guard.
        shade.with_context(wof_usage_skip=True).write({'value': 'درجة مخصصة', 'selected': False})
        self.profile.wof_flow_load()  # used to crash after a rename, and to re-select every shade
        self.assertEqual(shade.value, 'درجة مخصصة')
        self.assertFalse(shade.selected)
        self.assertEqual(len(self.profile.tint_shade_line_ids.filtered(lambda rec: rec.code == shade.code)), 1)

    def test_used_shade_is_locked(self):
        grade = self.film.film_category_line_ids.filtered('active')[:1]
        shade = self.profile.tint_shade_line_ids.filtered(lambda rec: rec.code == grade.code)
        self.assertTrue(shade)
        data = self.profile.wof_flow_load()
        row = self.row(data['tint'], 'shades', shade)
        self.assertTrue(row['used'])
        self.assertTrue(row['off_block'])  # an active film offers it
        self.assertTrue(data['tint']['method_locked'])
        with self.assertRaises(ValidationError):
            self.profile.wof_flow_apply('shade', {'id': shade.id, 'value': 'اسم آخر'})
        with self.assertRaises(ValidationError):
            self.profile.wof_flow_apply('shade', {'id': shade.id, 'selected': False})

    # -------------------------------------------------------- activities
    def test_activity_with_active_films_stays_on(self):
        line = self.profile.activity_line_ids.filtered(lambda rec: rec.activity_type == 'tint')
        data = self.profile.wof_flow_load()
        row = self.row(data, 'activities', line)
        self.assertTrue(row['used'])
        self.assertTrue(row['off_block'])
        with self.assertRaises(ValidationError):
            self.profile.wof_flow_apply('activity', {'id': line.id, 'selected': False})
        with self.assertRaises(ValidationError):
            self.profile.wof_flow_apply('activity', {'id': line.id, 'name': 'اسم آخر'})

    # -------------------------------------------------------- components
    def test_component_lock_follows_orders(self):
        part = self.part
        self.assertTrue(part.wof_in_use)
        self.assertFalse(part.wof_locked)  # only priced in a film: a rename shows in the film
        part.name = 'جزء الحماية المعدّل'
        with self.assertRaises(ValidationError):
            part.part_type = 'service_area'
        with self.assertRaises(ValidationError):
            part.unlink()
        self.make_order(self.master_size(self.size_line()))
        part.invalidate_recordset(['wof_in_use', 'wof_locked'])
        self.assertTrue(part.wof_locked)
        with self.assertRaises(ValidationError):
            part.name = 'اسم ثالث'
        with self.assertRaises(ValidationError):
            part.active = False  # an open order needs it
        part.priority_part = 5  # settings stay editable

    def test_option_used_by_an_order_is_kept(self):
        option = self.root['wof.car.part.options'].create({'code': 'USE-OPT', 'name': 'خيار الحماية'})
        self.part.part_options_ids = [(4, option.id)]
        with self.assertRaises(ValidationError):
            option.unlink()  # a component offers it
        order = self.make_order(self.master_size(self.size_line()))
        order.line_ids._write_line_internal({'option_ids': [(4, option.id)]})
        self.part.part_options_ids = [(3, option.id)]
        option.invalidate_recordset(['wof_in_use'])
        self.assertTrue(option.wof_in_use)
        with self.assertRaises(ValidationError):
            option.code = 'NEW-CODE'
        option.active = False  # stopping keeps it on the order
        self.assertIn(option, order.line_ids.with_context(active_test=False).option_ids)

    # ------------------------------------------------------------ sections
    def test_extras_on_order_stay_visible(self):
        self.assertFalse(self.profile.ui_extras)
        order = self.make_order(self.master_size(self.size_line()))
        self.assertNotIn(',extras,', order.wof_ui_sections)
        product = self.root['product.product'].create({'name': 'ملحق الحماية', 'type': 'consu'})
        self.env['wof.installation.extra.line'].create({
            'order_id': order.id, 'product_id': product.id, 'quantity': 1, 'price_unit': 20})
        order.invalidate_recordset(['wof_ui_sections'])
        self.assertIn(',extras,', order.wof_ui_sections)
