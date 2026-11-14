# -*- coding: utf-8 -*-
"""«إرسال لفحص الجودة» when some services are not at 100%.

Lists the unfinished services with their progress and lets the supervisor or
technician mark them complete and send the order in one step.
"""

from markupsafe import Markup, escape

from odoo import api, fields, models, _


class WofQualitySendWizard(models.TransientModel):
    _name = 'wof.quality.send.wizard'
    _description = 'إرسال أمر التركيب لفحص الجودة'

    order_id = fields.Many2one('wof.installation.order', string='أمر التركيب', required=True, readonly=True)
    summary = fields.Html(string='الخدمات غير المكتملة', compute='_compute_summary', sanitize=False)

    @api.depends('order_id')
    def _compute_summary(self):
        for wizard in self:
            rows = []
            for line in wizard.order_id.line_ids.filtered(lambda rec: rec.execution_progress != 100):
                rows.append(Markup(
                    '<tr><td><b>%s</b><br/><small>%s</small></td><td>%s</td>'
                    '<td><span class="wof_q_meter"><i style="width:%s%%"></i></span> %s٪</td></tr>'
                ) % (escape(line.car_part_id.name or ''), escape(line.film_category_id.name or ''),
                     escape(line.technician_names or '—'), line.execution_progress, line.execution_progress))
            wizard.summary = Markup(
                '<table class="table table-sm wof_q_table"><thead><tr><th>الخدمة</th><th>الفنيون</th>'
                '<th>التقدم</th></tr></thead><tbody>%s</tbody></table>') % Markup('').join(rows)

    def action_complete_and_send(self):
        self.ensure_one()
        order = self.order_id
        for line in order.line_ids.filtered(lambda rec: rec.execution_progress != 100):
            if line.part_line_ids:
                parts = line.part_line_ids.filtered(lambda part: part.progress != 100)
                line.wof_area_update(parts.ids, {'progress': 100})
            else:
                line.wof_line_update({'execution_progress': 100})
        order._log_business_event('order.services_completed', details={'by': self.env.user.name})
        return order.with_context(wof_quality_no_wizard=True).action_submit_quality()
