# -*- coding: utf-8 -*-

from odoo import fields, models, _
from odoo.exceptions import ValidationError


class WofFilmSetupComponentDialogBulk(models.TransientModel):
    _inherit = 'wof.film.setup.component.dialog'

    selected_part_ids = fields.Many2many(
        'wof.car.parts',
        'wof_film_setup_component_dialog_bulk_rel',
        'dialog_id', 'part_id',
        string='المكونات المحددة',
        domain="[('company_id', '=', company_id), ('active', '=', True), ('part_type', '=', expected_type)]",
    )

    def action_confirm(self):
        self.ensure_one()

        # Editing an existing row intentionally keeps the original single-record
        # flow. Bulk selection is only used by the Add Component / Add Service Area
        # buttons so existing edit behaviour is not changed.
        if self.line_id:
            return super().action_confirm()

        parts = self.selected_part_ids
        if not parts:
            raise ValidationError(_('حدد مكوّنًا واحدًا على الأقل قبل الإضافة.'))

        wrong = parts.filtered(
            lambda part: part.company_id != self.company_id
            or not part.active
            or part.part_type != self.expected_type
        )
        if wrong:
            raise ValidationError(_('بعض المكونات المحددة غير متاحة أو لا تطابق نوع الإضافة.'))

        if self.expected_type == 'service_area':
            empty_areas = parts.filtered(
                lambda part: not part.template_ids.filtered('active')
                and not part.service_area_part_ids
            )
            if empty_areas:
                raise ValidationError(
                    _('مناطق الخدمة التالية لا تحتوي على نماذج أو أجزاء: %s')
                    % '، '.join(empty_areas.mapped('name'))
                )

        existing_ids = set(
            self.wizard_id.component_line_ids.filtered(
                lambda line: not line.is_child
            ).mapped('car_part_id').ids
        )
        to_add = parts.filtered(lambda part: part.id not in existing_ids)
        for part in to_add.sorted(lambda rec: (rec.priority_part, rec.name or '', rec.id)):
            self.wizard_id._append_component_master(part)

        if not to_add:
            raise ValidationError(_('جميع المكونات المحددة مضافة بالفعل لهذا الفيلم / الخدمة.'))

        return self.wizard_id._dialog_action()
