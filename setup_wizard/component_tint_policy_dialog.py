# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FilmSetupComponentLineTintPolicy(models.TransientModel):
    _inherit = 'wof.film.setup.component.line'

    default_tint_grade_id = fields.Many2one(
        'wof.film.category.lines', string='درجة اللون الافتراضية',
    )
    allowed_tint_grade_ids = fields.Many2many(
        'wof.film.category.lines',
        'wof_setup_component_line_allowed_tint_rel',
        'line_id', 'grade_id', string='درجات اللون المسموحة',
    )

    def action_edit(self):
        action = super().action_edit()
        self.ensure_one()
        if self.is_child or self.part_type != 'car_part' or not self.wizard_id.film_id.supports_color_grades:
            return action
        dialog = self.env['wof.film.setup.component.create.dialog'].search([
            ('edit_line_id', '=', self.id),
        ], order='id desc', limit=1)
        if dialog:
            part_line = self.wizard_id.film_id.film_part_line_ids.filtered(
                lambda rec: rec.car_part_id == self.car_part_id
            )[:1]
            dialog.write({
                'default_tint_grade_id': part_line.film_category_line_id.id if part_line else False,
                'allowed_tint_grade_ids': [(6, 0, part_line.allowed_grade_ids.ids if part_line else [])],
            })
        return action


class FilmSetupComponentCreateDialogTintPolicy(models.TransientModel):
    _inherit = 'wof.film.setup.component.create.dialog'

    film_id = fields.Many2one(related='wizard_id.film_id', readonly=True)
    show_tint_policy = fields.Boolean(compute='_compute_show_tint_policy')
    default_tint_grade_id = fields.Many2one(
        'wof.film.category.lines', string='درجة اللون الافتراضية',
        domain="[('header_id', '=', film_id), ('active', '=', True)]",
    )
    allowed_tint_grade_ids = fields.Many2many(
        'wof.film.category.lines',
        'wof_component_create_allowed_tint_rel',
        'dialog_id', 'grade_id', string='درجات اللون المسموحة',
        domain="[('header_id', '=', film_id), ('active', '=', True)]",
    )

    @api.depends('expected_type', 'wizard_id.film_id.supports_color_grades')
    def _compute_show_tint_policy(self):
        for record in self:
            record.show_tint_policy = bool(
                record.expected_type == 'car_part'
                and record.wizard_id.film_id
                and record.wizard_id.film_id.supports_color_grades
            )

    @api.constrains('default_tint_grade_id', 'allowed_tint_grade_ids')
    def _check_tint_policy(self):
        for record in self:
            if not record.default_tint_grade_id and not record.allowed_tint_grade_ids:
                continue
            if not record.show_tint_policy:
                raise ValidationError('إعدادات درجات اللون متاحة فقط لمكوّنات نشاط العزل الحراري.')
            wrong = record.allowed_tint_grade_ids.filtered(lambda grade: grade.header_id != record.film_id)
            if wrong or (record.default_tint_grade_id and record.default_tint_grade_id.header_id != record.film_id):
                raise ValidationError('درجات اللون المختارة يجب أن تكون من درجات اللون المحددة لهذا الفيلم.')
            if (record.default_tint_grade_id and record.allowed_tint_grade_ids
                    and record.default_tint_grade_id not in record.allowed_tint_grade_ids):
                raise ValidationError('درجة اللون الافتراضية يجب أن تكون ضمن درجات اللون المسموحة.')

    def _copy_tint_policy_to_component_line(self, part):
        self.ensure_one()
        if not self.show_tint_policy:
            return
        line = self.wizard_id.component_line_ids.filtered(
            lambda rec: not rec.is_child and rec.car_part_id == part
        )[:1]
        if line:
            line.write({
                'default_tint_grade_id': self.default_tint_grade_id.id or False,
                'allowed_tint_grade_ids': [(6, 0, self.allowed_tint_grade_ids.ids)],
            })

    def action_create_and_add(self):
        self.ensure_one()
        before = set(self.wizard_id.component_line_ids.filtered(lambda rec: not rec.is_child).mapped('car_part_id').ids)
        result = super().action_create_and_add()
        added = self.wizard_id.component_line_ids.filtered(
            lambda rec: not rec.is_child and rec.car_part_id.id not in before
        )[:1]
        if added:
            self._copy_tint_policy_to_component_line(added.car_part_id)
        return result

    def action_save_changes(self):
        self.ensure_one()
        part = self.edit_part_id
        result = super().action_save_changes()
        if part:
            self._copy_tint_policy_to_component_line(part)
        return result


class FilmSetupWizardTintPolicy(models.TransientModel):
    _inherit = 'wof.film.setup.wizard'

    def _prepare_component_lines(self):
        result = super()._prepare_component_lines()
        for wizard in self:
            if not wizard.film_id or not wizard.film_id.supports_color_grades:
                continue
            for line in wizard.component_line_ids.filtered(lambda rec: not rec.is_child and rec.part_type == 'car_part'):
                part_line = wizard.film_id.film_part_line_ids.filtered(
                    lambda rec: rec.car_part_id == line.car_part_id
                )[:1]
                if part_line:
                    line.write({
                        'default_tint_grade_id': part_line.film_category_line_id.id or False,
                        'allowed_tint_grade_ids': [(6, 0, part_line.allowed_grade_ids.ids)],
                    })
        return result

    def _save_components(self):
        result = super()._save_components()
        for wizard in self:
            if not wizard.film_id or not wizard.film_id.supports_color_grades:
                continue
            for line in wizard.component_line_ids.filtered(
                lambda rec: not rec.is_child and rec.selected and rec.part_type == 'car_part'
            ):
                part_line = wizard.film_id.film_part_line_ids.filtered(
                    lambda rec: rec.car_part_id == line.car_part_id
                )[:1]
                if part_line:
                    part_line.write({
                        'film_category_line_id': line.default_tint_grade_id.id or False,
                        'allowed_grade_ids': [(6, 0, line.allowed_tint_grade_ids.ids)],
                    })
        return result
