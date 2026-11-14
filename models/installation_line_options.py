# -*- coding: utf-8 -*-
"""Extra options of a component and colour-grade warnings on the order.

* Options (خيارات إضافية): each component lists the options that may be chosen
  on it, and whether choosing at least one is required. The order service keeps
  the chosen ones; a required component without options blocks confirmation.
* Grade warnings: a component may allow only some colour grades (set per film
  component with the 💧 button). Choosing another grade is allowed but shows
  the component's warning text, on screen and on the printed order for the
  customer's signature. Parts of a service area follow the rule of the same
  part in the same film.
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

DEFAULT_GRADE_WARNING = 'درجة اللون المختارة غير مسموحة لهذا المكوّن.'


def _grade_policy(env, film, part):
    """Rule of ``part`` in ``film``: its component line, or the hidden line the film
    editor keeps for a part that is only used inside a service area."""
    if not film or not part:
        return env['wof.film.parts.lines']
    return env['wof.film.parts.lines'].search([
        ('header_id', '=', film.id), ('car_part_id', '=', part.id),
    ], order='part_selected desc, id', limit=1)


class WofOrderLineOptions(models.Model):
    _inherit = 'wof.installation.order.line'

    option_ids = fields.Many2many(
        'wof.car.part.options', 'wof_order_line_option_rel', 'line_id', 'option_id',
        string='الخيارات الإضافية', copy=False,
        domain="[('id', 'in', available_option_ids)]",
    )
    available_option_ids = fields.Many2many(related='car_part_id.part_options_ids', string='الخيارات المتاحة')
    options_required = fields.Boolean(related='car_part_id.part_options_required', string='الخيارات إجبارية')
    option_names = fields.Char(string='أسماء الخيارات', compute='_compute_option_names')
    options_missing = fields.Boolean(string='خيارات إجبارية ناقصة', compute='_compute_option_names')
    tint_warning_count = fields.Integer(string='تحذيرات الدرجة', compute='_compute_tint_warning_count')

    @api.depends('option_ids', 'car_part_id.part_options_required', 'car_part_id.part_options_ids')
    def _compute_option_names(self):
        for line in self:
            line.option_names = '، '.join(line.option_ids.mapped('name')) or False
            line.options_missing = bool(line.options_required and line.available_option_ids and not line.option_ids)

    @api.depends('has_tint_warning', 'part_line_ids.tint_warning')
    def _compute_tint_warning_count(self):
        for line in self:
            line.tint_warning_count = int(bool(line.has_tint_warning)) + len(
                line.part_line_ids.filtered('tint_warning'))

    def _wof_grade_warnings(self):
        """[(label, warning)] for the printed order and the screen."""
        self.ensure_one()
        result = []
        if self.has_tint_warning:
            result.append((self.car_part_id.name, self.tint_warning))
        for part in self.part_line_ids.filtered('tint_warning'):
            result.append(('%s / %s' % (self.car_part_id.name, part.part_id.name), part.tint_warning))
        return result

    def _validate_ready_for_confirmation(self):
        result = super()._validate_ready_for_confirmation()
        missing = self.filtered('options_missing')
        if missing:
            raise ValidationError(_('اختر الخيارات الإضافية الإجبارية للمكوّنات: %s.')
                                  % '، '.join(missing.car_part_id.mapped('name')))
        return result

    def write(self, vals):
        if 'option_ids' in vals and not self.env.context.get('wof_order_line_internal_token'):
            for line in self:
                if line.order_id.state not in ('draft', 'scheduled', 'intake'):
                    raise ValidationError(_('لا يمكن تغيير الخيارات الإضافية بعد بدء التنفيذ.'))
                if not line._wof_is_team_lead():
                    raise ValidationError(_('تحديد الخيارات الإضافية متاح للاستقبال أو المشرف.'))
        return super().write(vals)


class WofOrderLinePartTint(models.Model):
    _inherit = 'wof.installation.order.line.part'

    tint_warning = fields.Char(string='تحذير الدرجة', compute='_compute_tint_warning')

    @api.depends('grade_id', 'part_id', 'line_id.film_category_id')
    def _compute_tint_warning(self):
        for part in self:
            part.tint_warning = False
            if not part.grade_id or not part.line_id.supports_color_grades:
                continue
            policy = _grade_policy(self.env, part.line_id.film_category_id, part.part_id)
            if policy.allowed_grade_ids and part.grade_id not in policy.allowed_grade_ids:
                part.tint_warning = part.part_id.warning_msg or DEFAULT_GRADE_WARNING


class WofOrderGradeWarnings(models.Model):
    _inherit = 'wof.installation.order'

    def wof_grade_warnings(self):
        """All grade warnings of the order: [(component, warning)]."""
        self.ensure_one()
        result = []
        for line in self.line_ids:
            result += line._wof_grade_warnings()
        return result

    def action_print_order(self):
        self.ensure_one()
        return self.env.ref('yousentech_wo_v4.action_report_installation_order').report_action(self)
