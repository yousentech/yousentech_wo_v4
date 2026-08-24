# -*- coding: utf-8 -*-

from odoo import fields, models, _
from odoo.exceptions import AccessError, ValidationError


class WofActivityHub(models.TransientModel):
    _name = 'wof.activity.hub'
    _description = 'بوابة الأنشطة المفعلة'

    profile_id = fields.Many2one(
        'wof.company.profile', string='مركز التهيئة', required=True,
        ondelete='cascade', readonly=True,
    )
    company_id = fields.Many2one(
        'res.company', string='الشركة', required=True, readonly=True,
    )
    view_state = fields.Selection(
        [('activities', 'الأنشطة'), ('films', 'الأفلام والخدمات')],
        default='activities', required=True,
    )
    selected_activity_id = fields.Many2one(
        'wof.service.type', string='النشاط الحالي', readonly=True,
    )
    activity_line_ids = fields.One2many(
        'wof.activity.hub.activity', 'hub_id', string='الأنشطة المفعلة',
    )
    film_line_ids = fields.One2many(
        'wof.activity.hub.film', 'hub_id', string='أفلام وخدمات النشاط',
    )
    activity_count = fields.Integer(string='عدد الأنشطة', compute='_compute_counts')
    film_count = fields.Integer(string='عدد الأفلام والخدمات', compute='_compute_counts')

    def _compute_counts(self):
        for wizard in self:
            wizard.activity_count = len(wizard.activity_line_ids)
            wizard.film_count = len(wizard.film_line_ids)

    def _ensure_access(self):
        self.ensure_one()
        if self.company_id not in self.env.companies:
            raise AccessError(_('لا يمكنك إدارة أنشطة شركة غير مسموحة للمستخدم الحالي.'))
        return True

    def _refresh_activities(self):
        self.ensure_one()
        self._ensure_access()
        self.activity_line_ids.unlink()
        activities = self.env['wof.service.type'].search([
            ('company_id', '=', self.company_id.id),
            ('active', '=', True),
        ], order='code, name')
        Line = self.env['wof.activity.hub.activity']
        for activity in activities:
            Line.create({'hub_id': self.id, 'activity_id': activity.id})
        return activities

    def _select_activity(self, activity):
        self.ensure_one()
        self._ensure_access()
        if activity.company_id != self.company_id or not activity.active:
            raise ValidationError(_('النشاط المحدد غير متاح ضمن شركة مركز التهيئة الحالي.'))
        self.write({'view_state': 'films', 'selected_activity_id': activity.id})
        self._refresh_films()
        return self._reopen_hub()

    def _refresh_films(self):
        self.ensure_one()
        self._ensure_access()
        self.film_line_ids.unlink()
        if not self.selected_activity_id:
            return self.env['wof.film.category']
        films = self.env['wof.film.category'].with_context(active_test=False).search([
            ('company_id', '=', self.company_id.id),
            ('service_type_id', '=', self.selected_activity_id.id),
        ], order='sequence, name')
        Line = self.env['wof.activity.hub.film']
        for film in films:
            Line.create({'hub_id': self.id, 'film_id': film.id})
        return films

    def _reopen_hub(self):
        """Re-open the same transient wizard record so parent-state changes are
        rendered reliably inside the modal. A plain client reload can leave an
        embedded x2many card view showing the previous parent state in Odoo 17.
        """
        self.ensure_one()
        view = self.env.ref('yousentech_wo_v4.view_wof_activity_hub_form')
        return {
            'type': 'ir.actions.act_window',
            'name': _('الأنشطة المفعلة'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(view.id, 'form')],
            'target': 'new',
            'context': dict(self.env.context),
        }

    def action_back_to_activities(self):
        self.ensure_one()
        self.write({'view_state': 'activities', 'selected_activity_id': False})
        self.film_line_ids.unlink()
        self._refresh_activities()
        return self._reopen_hub()

    def action_open_films(self):
        """Validator-safe fallback; card actions are implemented on activity lines."""
        self.ensure_one()
        if self.selected_activity_id:
            self.write({'view_state': 'films'})
            self._refresh_films()
            return self._reopen_hub()
        return False

    def action_configure(self):
        """Validator-safe fallback; film-card actions are implemented on film lines."""
        self.ensure_one()
        return False

    def action_add_film(self):
        self.ensure_one()
        self._ensure_access()
        if not self.selected_activity_id:
            raise ValidationError(_('اختر نشاطًا قبل إضافة فيلم أو خدمة.'))
        wizard = self.env['wof.film.setup.wizard'].create_for_activity(
            self.selected_activity_id, hub=self,
        )
        return wizard._dialog_action()


class WofActivityHubActivity(models.TransientModel):
    _name = 'wof.activity.hub.activity'
    _description = 'كارد نشاط في بوابة التهيئة'
    _order = 'id'

    hub_id = fields.Many2one('wof.activity.hub', required=True, ondelete='cascade')
    activity_id = fields.Many2one('wof.service.type', required=True, ondelete='cascade')
    name = fields.Char(related='activity_id.name', readonly=True)
    description = fields.Text(related='activity_id.description', readonly=True)
    supports_color_grades = fields.Boolean(related='activity_id.supports_color_grades', readonly=True)
    film_count = fields.Integer(related='activity_id.film_count', readonly=True)
    parts_count = fields.Integer(related='activity_id.parts_count', readonly=True)
    active = fields.Boolean(related='activity_id.active', readonly=True)

    def action_open_films(self):
        self.ensure_one()
        return self.hub_id._select_activity(self.activity_id)


class WofActivityHubFilm(models.TransientModel):
    _name = 'wof.activity.hub.film'
    _description = 'كارد فيلم أو خدمة في بوابة التهيئة'
    _order = 'id'

    hub_id = fields.Many2one('wof.activity.hub', required=True, ondelete='cascade')
    film_id = fields.Many2one('wof.film.category', required=True, ondelete='cascade')
    name = fields.Char(related='film_id.name', readonly=True)
    description = fields.Text(related='film_id.description', readonly=True)
    item_type = fields.Selection(related='film_id.item_type', readonly=True)
    active = fields.Boolean(related='film_id.active', readonly=True)
    configuration_ready = fields.Boolean(related='film_id.configuration_ready', readonly=True)
    configuration_note = fields.Char(related='film_id.configuration_note', readonly=True)
    parts_count = fields.Integer(related='film_id.parts_count', readonly=True)
    grade_count = fields.Integer(related='film_id.grade_count', readonly=True)
    car_size_count = fields.Integer(related='film_id.car_size_count', readonly=True)
    pricing_summary = fields.Char(related='film_id.pricing_summary', readonly=True)
    commission_summary = fields.Char(related='film_id.commission_summary', readonly=True)
    supports_color_grades = fields.Boolean(related='film_id.supports_color_grades', readonly=True)

    def action_configure(self):
        self.ensure_one()
        action = self.film_id.action_configure()
        action['target'] = 'new'
        action.setdefault('context', {})
        action['context'].update({'wof_activity_hub_id': self.hub_id.id})
        return action
