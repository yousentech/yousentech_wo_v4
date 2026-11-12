# -*- coding: utf-8 -*-
"""Order data policy: which installation-order fields are required, optional or
hidden, as chosen in the guided setup ("بيانات أمر التركيب").

Each policy key maps to one order field and to the workflow stage where it is
checked, so a field is only demanded when the order reaches that stage:

* confirm  — customer and vehicle data, when the order is confirmed;
* intake   — odometer and sticker removal, when the intake is completed;
* execute  — technician, when execution starts;
* delivery — completion date, when the car is delivered.

All missing fields of a stage are reported together in one message.
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from ..setup_wizard.setup_wizard import FIELD_RULES, OPERATION_FIELD_DEFAULTS, STAGE_LABELS

DEFAULT_POLICY = {
    key: ('hid' if hidden else ('req' if required else 'opt'))
    for key, _label, required, hidden, _sequence in OPERATION_FIELD_DEFAULTS
}
LABELS = {key: label for key, label, _r, _h, _s in OPERATION_FIELD_DEFAULTS}


class WofInstallationOrderFields(models.Model):
    _inherit = 'wof.installation.order'

    agency_id = fields.Many2one('wof.car.agency', string='الوكالة', ondelete='restrict')
    partner_category_ids = fields.Many2many(
        related='partner_id.category_id', string='فئة العميل', readonly=False,
    )
    salesperson_id = fields.Many2one(
        'salesman', string='المندوب', ondelete='restrict', index=True,
        domain="[('id', 'in', salesman_candidate_ids)]",
        help='من مندوبي الفرع المسندين لفرع الأمر؛ يُنقل إلى أمر البيع والفاتورة.',
    )
    sticker_removal = fields.Selection(
        [('not_needed', 'لا تحتاج'), ('needed', 'تحتاج إزالة لواصق'), ('done', 'تمت الإزالة')],
        string='إزالة اللواصق', copy=False,
    )
    completion_date = fields.Datetime(
        string='تاريخ الإنجاز', copy=False,
        help='يُعبّأ تلقائيًا عند انتهاء التنفيذ، ويمكن تعديله.',
    )
    # Comma-wrapped key lists (",plate,vin,") used by the form to hide fields and
    # mark the required ones; computed from the setup on every read.
    wof_hidden_fields = fields.Char(compute='_compute_wof_field_policy')
    wof_required_fields = fields.Char(compute='_compute_wof_field_policy')

    @api.model
    def _wof_field_policy(self):
        """{key: 'req' | 'opt' | 'hid'} from the shared setup, with safe defaults."""
        policy = dict(DEFAULT_POLICY)
        profile = self.env['wof.company.profile']._wof_get_profile()
        for line in profile.operation_field_line_ids if profile else []:
            policy[line.field_key] = 'hid' if line.hidden else ('req' if line.required else 'opt')
        return policy

    @api.depends('state')
    @api.depends_context('uid')
    def _compute_wof_field_policy(self):
        policy = self._wof_field_policy()
        hidden = ',' + ','.join(k for k, v in policy.items() if v == 'hid') + ','
        required = ',' + ','.join(k for k, v in policy.items() if v == 'req') + ','
        for order in self:
            order.wof_hidden_fields = hidden
            order.wof_required_fields = required

    def _wof_field_required(self, key):
        return self._wof_field_policy().get(key) == 'req'

    def _wof_check_stage_fields(self, stage, extra=None):
        """Raise one message listing every required field of ``stage`` left empty."""
        self.ensure_one()
        policy = self._wof_field_policy()
        missing = list(extra or [])
        for key, (field_name, field_stage) in FIELD_RULES.items():
            if field_stage != stage or policy.get(key) != 'req':
                continue
            if key == 'mobile':
                empty = not (self.partner_id.mobile or self.partner_id.phone)
            else:
                empty = not self[field_name]
            if empty:
                missing.append(LABELS.get(key, field_name))
        if missing:
            raise ValidationError(_('أكمل البيانات التالية %s: %s.') % (STAGE_LABELS[stage], '، '.join(missing)))
