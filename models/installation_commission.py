# -*- coding: utf-8 -*-
"""Technician commission ledger.

One entry per technician and service. Entries are never edited by hand nor
deleted: every change goes through the events below and is written in the
entry history.

* Sending the order to quality creates the entries as *pending* (estimates
  that follow the technicians and the settings).
* The commission event of the film (delivery, or invoice posting) freezes them
  as *approved*: amount, distribution and technician weights at that moment.
  On delivery, only technicians who finished their tasks share it.
* A credit note reverses the frozen entries in the same proportions they were
  approved with (whatever the settings became): an unpaid entry fully returned
  is cancelled, otherwise a negative *reversal* entry is added.
* Cancelling the order cancels what is not paid and reverses what is.
* The manager may recalculate an order from the latest settings (with a
  reason): unpaid entries are *replaced*, paid ones get an *adjustment* for the
  difference. He may also add a manual adjustment.

The ledger is system managed: users only read it (supervisors their branches,
managers all), and every write goes through ``_wof_ledger()``.
"""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_compare, float_is_zero

from .installation_commission_split import DISTRIBUTIONS

LIVE_STATES = ('pending', 'approved', 'paid')
INTERNAL_KEY = 'wof_commission_internal'


class WofTechnicianCommission(models.Model):
    _name = 'wof.technician.commission'
    _description = 'عمولة فني'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char(string='المرجع', readonly=True, copy=False, default='/')
    company_id = fields.Many2one('res.company', string='الفرع', required=True, readonly=True, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id', string='العملة')
    order_id = fields.Many2one('wof.installation.order', string='أمر التركيب', readonly=True, index=True,
                               ondelete='restrict')
    line_id = fields.Many2one('wof.installation.order.line', string='الخدمة', readonly=True, index=True,
                              ondelete='restrict')
    employee_id = fields.Many2one('hr.employee', string='الفني', required=True, readonly=True, index=True,
                                  ondelete='restrict')
    film_category_id = fields.Many2one(related='line_id.film_category_id', store=True, string='الفيلم/الخدمة')
    car_part_id = fields.Many2one(related='line_id.car_part_id', store=True, string='المكوّن')
    vehicle_plate = fields.Char(related='order_id.vehicle_plate', store=True, string='اللوحة')
    entry_type = fields.Selection([
        ('normal', 'عمولة'), ('reversal', 'عكس'), ('adjustment', 'تسوية'),
    ], string='النوع', required=True, readonly=True, default='normal', tracking=True)
    state = fields.Selection([
        ('pending', 'معلّقة'), ('approved', 'معتمدة'), ('paid', 'مدفوعة'),
        ('cancelled', 'ملغاة'), ('replaced', 'مستبدلة'),
    ], string='الحالة', required=True, readonly=True, default='pending', index=True, tracking=True)
    distribution = fields.Selection(
        DISTRIBUTIONS + [('manual', 'يدوي')], string='طريقة التوزيع', readonly=True, tracking=True)
    weight = fields.Float(string='الوزن', readonly=True, tracking=True,
                          help='وزن الفني عند التوزيع حسب نسبة الفني (نسبته في فريق العمل وقتها).')
    service_commission = fields.Monetary(string='عمولة الخدمة', readonly=True, tracking=True,
                                         help='عمولة الخدمة كاملة قبل توزيعها على الفنيين.')
    amount = fields.Monetary(string='نصيب الفني', readonly=True, tracking=True)
    commission_event = fields.Selection(
        [('delivery', 'عند التسليم'), ('invoice', 'عند ترحيل الفاتورة')], string='الاستحقاق', readonly=True)
    approved_at = fields.Datetime(string='تاريخ الاعتماد', readonly=True, tracking=True)
    approved_by_id = fields.Many2one('res.users', string='اعتمدها', readonly=True)
    source = fields.Char(string='المصدر', readonly=True, tracking=True)
    reason = fields.Text(string='السبب', readonly=True)
    reversed_entry_id = fields.Many2one('wof.technician.commission', string='تعكس العمولة', readonly=True,
                                        index=True, ondelete='restrict')
    reversal_ids = fields.One2many('wof.technician.commission', 'reversed_entry_id', string='قيود العكس')
    refund_move_id = fields.Many2one('account.move', string='الإشعار الدائن', readonly=True, index=True,
                                     ondelete='restrict')
    state_before_cancel = fields.Char(readonly=True, copy=False)

    # ------------------------------------------------------------ guards
    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get(INTERNAL_KEY):
            raise AccessError(_('سجل العمولات يُدار تلقائيًا من أوامر التركيب ولا يُنشأ يدويًا.'))
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('wof.technician.commission') or '/'
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.context.get(INTERNAL_KEY) and set(vals) - {'message_main_attachment_id'}:
            raise AccessError(_('العمولة لا تُعدَّل يدويًا. للتصحيح استخدم «إعادة احتساب العمولة» أو «تسوية عمولة».'))
        return super().write(vals)

    def unlink(self):
        raise UserError(_('لا تُحذف العمولات؛ كل تغيير يبقى في سجلها.'))

    def _wof_log(self, body):
        for entry in self:
            entry.message_post(body=body, message_type='comment', subtype_xmlid='mail.mt_note')

    def action_open_order(self):
        self.ensure_one()
        return self.order_id.get_formview_action() if self.order_id else False


class WofCommissionEngine(models.AbstractModel):
    """Shared helpers: the single privileged access to the ledger."""
    _name = 'wof.commission.engine'
    _description = 'محرك العمولات'

    @api.model
    def _wof_ledger(self):
        # The only privileged access of the commission engine: entries are
        # written by the order events (delivery, invoice posting by an
        # accountant, credit notes...) for users who may not read the ledger.
        return self.env['wof.technician.commission'].sudo().with_context(**{INTERNAL_KEY: True})


class WofOrderLineCommission(models.Model):
    _inherit = 'wof.installation.order.line'

    commission_entry_ids = fields.One2many('wof.technician.commission', 'line_id', string='عمولات الفنيين',
                                           groups='yousentech_wo_v4.group_wo_supervisor,yousentech_wo_v4.group_wo_manager')

    def _wof_commission_label(self):
        self.ensure_one()
        return ' · '.join(name for name in (self.film_category_id.name, self.car_part_id.name) if name)

    # ------------------------------------------------------------ amounts
    def _wof_commission_total(self, per_unit=None):
        """Commission of the whole service, following the setup."""
        self.ensure_one()
        profile = self.env['wof.company.profile']._wof_get_profile()
        currency = self.currency_id or self.order_id.company_id.currency_id
        qty = self.quantity or 1.0
        net = self.unit_price * qty - (self.discount_amount or 0.0)
        if profile and profile.commission_free_service == 'none' and float_compare(
                net, 0.0, precision_rounding=currency.rounding) <= 0:
            return 0.0
        per_unit = self.configured_commission if per_unit is None else per_unit
        rule = self._wof_rule_line()
        if profile and profile.commission_percent_base == 'actual' and rule.commission_value_type == 'percent' \
                and self.configured_unit_price:
            return currency.round(max(net, 0.0) * per_unit / self.configured_unit_price)
        return currency.round(per_unit * qty)

    def _wof_open_tasks(self):
        """{(part id or False, employee id)} of the unfinished tasks of this service."""
        self.ensure_one()
        tasks = self.env['wof.technician.task'].search([('line_id', '=', self.id), ('done', '=', False)])
        return {(task.part_id.id or False, task.employee_id.id) for task in tasks}

    def _wof_commission_plan(self, total=None, completed_only=False):
        """(rule, {employee_id: (amount, weight)}) rounded so the sum is the total."""
        self.ensure_one()
        total = self._wof_commission_total() if total is None else total
        open_tasks = self._wof_open_tasks() if completed_only else set()
        rule, shares, weights = self._wof_commission_shares(total, excluded=open_tasks)
        currency = self.currency_id or self.order_id.company_id.currency_id
        rounded = {emp: currency.round(amount) for emp, amount in shares.items()}
        if rounded:
            diff = currency.round(total - sum(rounded.values()))
            if not float_is_zero(diff, precision_rounding=currency.rounding):
                biggest = max(rounded, key=lambda emp: rounded[emp])
                rounded[biggest] = currency.round(rounded[biggest] + diff)
        return rule, {emp: (amount, weights.get(emp, 0.0)) for emp, amount in rounded.items()}

    def _wof_refunded_fraction(self):
        """Share of the service returned by posted credit notes (0..1)."""
        self.ensure_one()
        sale_lines = self.env['sale.order.line'].search([('wof_order_line_id', '=', self.id)])
        if not sale_lines:
            return 0.0
        refunds = self.env['account.move.line'].search([
            ('sale_line_ids', 'in', sale_lines.ids), ('move_id.move_type', '=', 'out_refund'),
            ('move_id.state', '=', 'posted'), ('display_type', '=', 'product'),
        ])
        qty = sum(refunds.mapped('quantity'))
        return min(1.0, qty / (self.quantity or 1.0))

    # ------------------------------------------------------------ ledger ops
    def _wof_entries(self, types=('normal',), states=LIVE_STATES):
        ledger = self.env['wof.commission.engine']._wof_ledger()
        return ledger.search([('line_id', 'in', self.ids), ('entry_type', 'in', types), ('state', 'in', states)])

    def _wof_entry_values(self, employee_id, amount, weight, rule, total, state, source):
        self.ensure_one()
        return {
            'company_id': self.order_id.company_id.id, 'order_id': self.order_id.id, 'line_id': self.id,
            'employee_id': employee_id, 'entry_type': 'normal', 'state': state,
            'distribution': rule, 'weight': weight, 'service_commission': total, 'amount': amount,
            'commission_event': self.commission_event or 'delivery', 'source': source,
        }

    def _wof_commission_sync(self, approve=False, source=False):
        """Pending entries follow the service; ``approve`` freezes them."""
        ledger = self.env['wof.commission.engine']._wof_ledger()
        now = fields.Datetime.now()
        for line in self:
            if not line.id or not line.film_category_id:
                continue
            entries = line._wof_entries()
            if entries.filtered(lambda entry: entry.state in ('approved', 'paid')):
                continue  # frozen: only reversal, recalculation or adjustment change it
            if line._wof_entries(types=('normal', 'reversal'), states=LIVE_STATES + ('cancelled',)).filtered(
                    'refund_move_id'):
                continue  # already returned by a credit note
            # Freeze only once the technicians are locked (sent to quality); an
            # invoice posted earlier (payment first) approves at that moment.
            freeze = (approve or line.commission_state == 'approved') \
                and line.order_id.state in ('quality', 'ready', 'delivered')
            completed_only = freeze and (line.commission_event or 'delivery') == 'delivery' \
                and not self.env.context.get('wof_commission_no_task_check')
            total = line._wof_commission_total()
            rule, plan = line._wof_commission_plan(total, completed_only=completed_only)
            if freeze and total and not plan and line.technician_ids:
                line.order_id.message_post(body=_(
                    'لم تُعتمد عمولة «%s»: لا يوجد فني أنهى مهامه في هذه الخدمة. راجعها من «إعادة احتساب العمولة».'
                ) % line._wof_commission_label())
                continue
            by_employee = {entry.employee_id.id: entry for entry in entries}
            for emp, (amount, weight) in plan.items():
                if float_is_zero(amount, precision_rounding=line.currency_id.rounding or 0.01):
                    continue
                entry = by_employee.pop(emp, None)
                values = {'distribution': rule, 'weight': weight, 'service_commission': total, 'amount': amount}
                if entry:
                    changed = {key: value for key, value in values.items() if entry[key] != value}
                    if changed:
                        entry.write(changed)
                else:
                    ledger.create(line._wof_entry_values(
                        emp, amount, weight, rule, total, 'pending', source or _('إرسال الأمر للجودة')))
            for entry in by_employee.values():
                entry.write({'state': 'cancelled', 'source': _('خرج الفني من الخدمة أو لم يُنجز مهامه')})
            if freeze:
                pending = line._wof_entries(states=('pending',))
                pending.write({'state': 'approved', 'approved_at': now, 'approved_by_id': self.env.user.id,
                               'source': source or _('الاعتماد')})

    def _wof_engine_lines(self):
        """These services read with the engine rights (the event may come from an accountant)."""
        return self.env['wof.commission.engine']._wof_ledger().env['wof.installation.order.line'].browse(self.ids)

    def _wof_set_commission(self, event, approved):
        target = 'approved' if approved else 'pending'
        lines = self.filtered(lambda line: (line.commission_event or 'delivery') == event
                              and line.commission_state != target)
        result = super()._wof_set_commission(event, approved)
        if lines:
            default = _('تسليم السيارة') if event == 'delivery' else _('ترحيل الفاتورة')
            source = self.env.context.get('wof_commission_source') or default
            engine = lines._wof_engine_lines()
            if approved:
                engine._wof_commission_sync(approve=True, source=source)
            else:
                engine._wof_commission_unapprove(source)
        return result

    def _wof_commission_unapprove(self, source):
        """Invoice back to draft or cancelled: approved returns to pending, paid is reversed."""
        for entry in self._wof_entries(states=('approved', 'paid')):
            if entry.state == 'approved':
                entry.write({'state': 'pending', 'approved_at': False, 'approved_by_id': False, 'source': source})
            else:
                entry._wof_reverse_amount(entry.amount, source)

    def _wof_commission_reverse(self, fraction, move):
        """Return ``fraction`` of each frozen entry of these services (credit note ``move``)."""
        for entry in self._wof_entries():
            currency = entry.currency_id
            returned = -sum(entry.reversal_ids.filtered(lambda rev: rev.state in LIVE_STATES).mapped('amount'))
            remaining = currency.round(entry.amount - returned)
            amount = min(currency.round(entry.amount * fraction), remaining)
            if float_compare(amount, 0.0, precision_rounding=currency.rounding) <= 0:
                continue
            if entry.state in ('pending', 'approved') and not returned \
                    and float_compare(amount, entry.amount, precision_rounding=currency.rounding) >= 0:
                entry.write({'state': 'cancelled', 'state_before_cancel': entry.state,
                             'refund_move_id': move.id, 'source': _('مرتجع: %s') % move.name})
            else:
                entry._wof_reverse_amount(amount, _('مرتجع: %s') % move.name, move=move)


class WofTechnicianCommissionOps(models.Model):
    _inherit = 'wof.technician.commission'

    def _wof_reverse_amount(self, amount, source, move=None, reason=False):
        """Negative entry returning ``amount`` of this entry (same technician and service)."""
        self.ensure_one()
        reversal = self.env['wof.commission.engine']._wof_ledger().create({
            'company_id': self.company_id.id, 'order_id': self.order_id.id, 'line_id': self.line_id.id,
            'employee_id': self.employee_id.id, 'entry_type': 'reversal', 'state': 'approved',
            'distribution': self.distribution, 'weight': self.weight,
            'service_commission': self.service_commission, 'amount': -amount,
            'commission_event': self.commission_event, 'reversed_entry_id': self.id,
            'refund_move_id': move.id if move else False, 'source': source, 'reason': reason,
            'approved_at': fields.Datetime.now(), 'approved_by_id': self.env.uid,
        })
        self._wof_log(_('عُكس منها %(amount)s — %(source)s (%(ref)s).') % {
            'amount': amount, 'source': source, 'ref': reversal.name})
        return reversal


class WofOrderCommission(models.Model):
    _inherit = 'wof.installation.order'

    commission_entry_ids = fields.One2many('wof.technician.commission', 'order_id', string='عمولات الفنيين',
                                           groups='yousentech_wo_v4.group_wo_supervisor,yousentech_wo_v4.group_wo_manager')
    commission_count = fields.Integer(compute='_compute_commission_totals', string='العمولات',
                                      groups='yousentech_wo_v4.group_wo_supervisor,yousentech_wo_v4.group_wo_manager')
    commission_net = fields.Monetary(compute='_compute_commission_totals', string='صافي العمولات',
                                     groups='yousentech_wo_v4.group_wo_supervisor,yousentech_wo_v4.group_wo_manager')
    commission_summary_html = fields.Html(compute='_compute_commission_totals', string='نصيب الفنيين', sanitize=False,
                                          groups='yousentech_wo_v4.group_wo_supervisor,yousentech_wo_v4.group_wo_manager')

    def _compute_commission_totals(self):
        ledger = self.env['wof.commission.engine']._wof_ledger()
        for order in self:
            entries = ledger.search([('order_id', '=', order.id)]) if order.id else ledger
            live = entries.filtered(lambda entry: entry.state in LIVE_STATES)
            order.commission_count = len(entries)
            order.commission_net = sum(live.mapped('amount'))
            order.commission_summary_html = order._wof_commission_summary(live)

    def _wof_commission_summary(self, live):
        if not live:
            return '<p class="text-muted mb-0">لا توجد عمولات بعد؛ تُنشأ عند إرسال الأمر لفحص الجودة.</p>'
        rows = {}
        for entry in live:
            row = rows.setdefault(entry.employee_id.id, {'name': entry.employee_id.name, 'pending': 0.0,
                                                          'approved': 0.0, 'paid': 0.0})
            row[entry.state] += entry.amount
        symbol = self.currency_id.symbol or ''
        body = ''.join(
            '<tr><td>%s</td><td class="text-end">%.2f</td><td class="text-end">%.2f</td>'
            '<td class="text-end">%.2f</td><td class="text-end fw-bold">%.2f %s</td></tr>' % (
                row['name'], row['pending'], row['approved'], row['paid'],
                row['pending'] + row['approved'] + row['paid'], symbol)
            for row in rows.values())
        return ('<table class="table table-sm wof_com_table mb-0"><thead><tr><th>الفني</th>'
                '<th class="text-end">معلّقة</th><th class="text-end">معتمدة</th><th class="text-end">مدفوعة</th>'
                '<th class="text-end">الصافي</th></tr></thead><tbody>%s</tbody></table>') % body

    # ------------------------------------------------------------ events
    def action_submit_quality(self):
        result = super().action_submit_quality()
        for order in self.filtered(lambda rec: rec.state in ('quality', 'ready', 'delivered')):
            order.line_ids._wof_engine_lines()._wof_commission_sync(source=_('إرسال الأمر للجودة'))
        return result

    def action_cancel(self):
        result = super().action_cancel()
        for order in self.filtered(lambda rec: rec.state == 'cancelled'):
            source = _('إلغاء الأمر: %s') % (order.cancellation_reason or '')
            ledger = self.env['wof.commission.engine']._wof_ledger()
            entries = ledger.search([('order_id', '=', order.id), ('state', 'in', LIVE_STATES)])
            for entry in entries:
                if entry.state == 'paid':
                    if entry.entry_type != 'reversal':
                        returned = -sum(entry.reversal_ids.filtered(
                            lambda rev: rev.state in LIVE_STATES).mapped('amount'))
                        if entry.amount - returned > 0:
                            entry._wof_reverse_amount(entry.amount - returned, source)
                else:
                    entry.write({'state': 'cancelled', 'state_before_cancel': entry.state, 'source': source})
        return result

    # ------------------------------------------------------------ actions
    def _wof_commission_manager(self):
        if not self.env.user.has_group('yousentech_wo_v4.group_wo_manager'):
            raise AccessError(_('إعادة احتساب العمولة وتسويتها لمدير المركز فقط.'))

    def action_view_commissions(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('yousentech_wo_v4.action_wof_commissions')
        action['domain'] = [('order_id', '=', self.id)]
        action['context'] = {'search_default_live': 1}
        return action

    def action_open_commission_recalc(self):
        self.ensure_one()
        self._wof_commission_manager()
        if self.state in ('draft', 'scheduled', 'cancelled'):
            raise ValidationError(_('إعادة الاحتساب متاحة بعد بدء العمل وقبل الإلغاء.'))
        wizard = self.env['wof.commission.recalc.wizard'].create({'order_id': self.id})
        wizard._wof_fill_preview()
        return {
            'type': 'ir.actions.act_window', 'name': _('إعادة احتساب العمولة'),
            'res_model': 'wof.commission.recalc.wizard', 'res_id': wizard.id,
            'view_mode': 'form', 'target': 'new',
        }

    def action_open_commission_adjust(self):
        self.ensure_one()
        self._wof_commission_manager()
        return {
            'type': 'ir.actions.act_window', 'name': _('تسوية عمولة'),
            'res_model': 'wof.commission.adjust.wizard', 'view_mode': 'form', 'target': 'new',
            'context': {'default_order_id': self.id},
        }

    def _wof_commission_recalc_plan(self):
        """[{line, employee_id, old, new, paid}] from the latest settings."""
        self.ensure_one()
        engine_lines = self.env['wof.commission.engine']._wof_ledger().env['wof.installation.order.line']
        plan = []
        for line in engine_lines.browse(self.line_ids.ids):
            if not line.film_category_id:
                continue
            _part_line, price, commission, _source = line._pricing_configuration()
            per_unit = line._resolved_configured_commission(price, commission)
            accrued = line.commission_state == 'approved'
            completed_only = accrued and (line.commission_event or 'delivery') == 'delivery'
            factor = 1.0 - line._wof_refunded_fraction()
            total = line._wof_commission_total(per_unit=per_unit)
            rule, shares = line._wof_commission_plan(total * factor, completed_only=completed_only)
            live = line._wof_entries(types=('normal', 'reversal', 'adjustment'))
            employees = set(shares) | set(live.mapped('employee_id').ids)
            for emp in employees:
                mine = live.filtered(lambda entry: entry.employee_id.id == emp)
                new_amount, weight = shares.get(emp, (0.0, 0.0))
                plan.append({
                    'line': line, 'employee_id': emp, 'old': sum(mine.mapped('amount')), 'new': new_amount,
                    'weight': weight, 'rule': rule, 'total': total, 'per_unit': per_unit,
                    'paid': bool(mine.filtered(lambda entry: entry.state == 'paid')),
                    'state': 'approved' if accrued else 'pending',
                })
        return plan

    def _wof_commission_recalc_apply(self, reason):
        self.ensure_one()
        self._wof_commission_manager()
        reason = (reason or '').strip()
        if not reason:
            raise ValidationError(_('اكتب سبب إعادة احتساب العمولة.'))
        ledger = self.env['wof.commission.engine']._wof_ledger()
        source = _('إعادة احتساب: %s') % reason
        now = fields.Datetime.now()
        plan = self._wof_commission_recalc_plan()
        changes = []
        for line in {row['line'] for row in plan}:
            per_unit = next(row['per_unit'] for row in plan if row['line'] == line)
            if line.configured_commission != per_unit:
                line._write_line_internal({'configured_commission': per_unit})
            # Credit-note links are settled by the new figures (already net of returns).
            line._wof_entries(types=('normal',), states=('cancelled',)).filtered('refund_move_id').write(
                {'state_before_cancel': False})
        for row in plan:
            line, emp = row['line'], row['employee_id']
            currency = line.currency_id
            diff = currency.round(row['new'] - row['old'])
            if float_is_zero(diff, precision_rounding=currency.rounding):
                continue
            live = line._wof_entries(types=('normal', 'reversal', 'adjustment')).filtered(
                lambda entry: entry.employee_id.id == emp)
            if row['paid']:
                ledger.create({
                    'company_id': self.company_id.id, 'order_id': self.id, 'line_id': line.id,
                    'employee_id': emp, 'entry_type': 'adjustment', 'state': 'approved',
                    'distribution': row['rule'], 'weight': row['weight'], 'service_commission': row['total'],
                    'amount': diff, 'commission_event': line.commission_event or 'delivery',
                    'source': source, 'reason': reason, 'approved_at': now, 'approved_by_id': self.env.uid,
                })
            else:
                new_entry = ledger.browse()
                if not float_is_zero(row['new'], precision_rounding=currency.rounding):
                    values = line._wof_entry_values(emp, row['new'], row['weight'], row['rule'], row['total'],
                                                    row['state'], source)
                    values['reason'] = reason
                    if row['state'] == 'approved':
                        values.update(approved_at=now, approved_by_id=self.env.uid)
                    new_entry = ledger.create(values)
                live.write({'state': 'replaced', 'source': source})
                for old in live:
                    old._wof_log(_('استُبدلت بـ %s — %s') % (new_entry.name or _('لا شيء'), reason))
            changes.append('%s: %.2f ← %.2f' % (line._wof_employee_names([emp]).get(emp, ''), row['new'], row['old']))
        self._log_business_event('order.commission_recalculated', note=reason)
        self.message_post(body=_('أُعيد احتساب العمولة (%s). %s') % (
            reason, ' · '.join(changes) if changes else _('لا تغيير في المبالغ.')))
        return changes


class WofCommissionRecalcWizard(models.TransientModel):
    _name = 'wof.commission.recalc.wizard'
    _description = 'إعادة احتساب عمولة أمر تركيب'

    order_id = fields.Many2one('wof.installation.order', string='أمر التركيب', required=True, readonly=True)
    currency_id = fields.Many2one(related='order_id.currency_id')
    reason = fields.Text(string='السبب')
    line_ids = fields.One2many('wof.commission.recalc.wizard.line', 'wizard_id', string='المعاينة', readonly=True)
    has_paid = fields.Boolean(compute='_compute_has_paid')

    @api.depends('line_ids.paid')
    def _compute_has_paid(self):
        for wizard in self:
            wizard.has_paid = any(wizard.line_ids.mapped('paid'))

    def _wof_fill_preview(self):
        self.ensure_one()
        rows = self.order_id._wof_commission_recalc_plan()
        names = self.env['wof.installation.order.line']._wof_employee_names([row['employee_id'] for row in rows])
        self.line_ids = [(5, 0, 0)] + [(0, 0, {
            'service': row['line']._wof_commission_label(), 'employee_name': names.get(row['employee_id'], ''),
            'old_amount': row['old'], 'new_amount': row['new'], 'paid': row['paid'],
        }) for row in rows]

    def action_confirm(self):
        self.ensure_one()
        self.order_id._wof_commission_recalc_apply(self.reason)
        return {'type': 'ir.actions.act_window_close'}


class WofCommissionRecalcWizardLine(models.TransientModel):
    _name = 'wof.commission.recalc.wizard.line'
    _description = 'معاينة إعادة احتساب العمولة'

    wizard_id = fields.Many2one('wof.commission.recalc.wizard', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='wizard_id.currency_id')
    service = fields.Char(string='الخدمة')
    employee_name = fields.Char(string='الفني')
    old_amount = fields.Monetary(string='الحالي')
    new_amount = fields.Monetary(string='بعد الاحتساب')
    diff_amount = fields.Monetary(string='الفرق', compute='_compute_diff')
    paid = fields.Boolean(string='مدفوعة')

    @api.depends('old_amount', 'new_amount')
    def _compute_diff(self):
        for row in self:
            row.diff_amount = row.new_amount - row.old_amount


class WofCommissionAdjustWizard(models.TransientModel):
    _name = 'wof.commission.adjust.wizard'
    _description = 'تسوية عمولة فني'

    order_id = fields.Many2one('wof.installation.order', string='أمر التركيب', readonly=True)
    company_id = fields.Many2one('res.company', compute='_compute_company')
    currency_id = fields.Many2one(related='company_id.currency_id')
    employee_id = fields.Many2one('hr.employee', string='الفني', required=True,
                                  domain="[('company_id', 'in', [company_id, False])]")
    amount = fields.Monetary(string='المبلغ', required=True,
                             help='موجب يضاف للفني، وسالب يخصم منه.')
    reason = fields.Text(string='السبب', required=True)

    @api.depends('order_id')
    def _compute_company(self):
        for wizard in self:
            wizard.company_id = wizard.order_id.company_id or self.env.company

    def action_confirm(self):
        self.ensure_one()
        if not self.env.user.has_group('yousentech_wo_v4.group_wo_manager'):
            raise AccessError(_('تسوية العمولة لمدير المركز فقط.'))
        if float_is_zero(self.amount, precision_rounding=self.currency_id.rounding):
            raise ValidationError(_('أدخل مبلغ التسوية (موجب للإضافة، سالب للخصم).'))
        reason = (self.reason or '').strip()
        if not reason:
            raise ValidationError(_('اكتب سبب التسوية.'))
        members = self.env['wof.team.member']._wof_employees(self.company_id, 'technician')
        if self.employee_id not in members:
            raise ValidationError(_('«%s» ليس فنيًا في فريق فرع «%s».') % (self.employee_id.name, self.company_id.name))
        entry = self.env['wof.commission.engine']._wof_ledger().create({
            'company_id': self.company_id.id, 'order_id': self.order_id.id or False,
            'employee_id': self.employee_id.id, 'entry_type': 'adjustment', 'state': 'approved',
            'distribution': 'manual', 'amount': self.amount, 'source': _('تسوية يدوية'), 'reason': reason,
            'approved_at': fields.Datetime.now(), 'approved_by_id': self.env.uid,
        })
        if self.order_id:
            self.order_id._log_business_event('order.commission_adjusted', note=reason)
            self.order_id.message_post(body=_('تسوية عمولة %s للفني %s: %s') % (entry.name, self.employee_id.name, reason))
        return {'type': 'ir.actions.act_window_close'}


class AccountMoveCommission(models.Model):
    _inherit = 'account.move'

    def _wof_refund_fractions(self):
        """{service line: returned share} of a credit note (by quantity)."""
        self.ensure_one()
        engine = self.env['wof.commission.engine']._wof_ledger().env
        fractions = {}
        for aml in engine['account.move.line'].browse(self.invoice_line_ids.ids):
            if aml.display_type != 'product':
                continue
            service = aml.sale_line_ids.wof_order_line_id[:1]
            if service:
                fractions[service] = fractions.get(service, 0.0) + aml.quantity / (service.quantity or 1.0)
        return fractions

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        for move in posted.filtered(lambda rec: rec.move_type == 'out_refund'):
            for service, fraction in move._wof_refund_fractions().items():
                service._wof_commission_reverse(min(1.0, fraction), move)
        return posted

    def _wof_commission_undo_refund(self):
        refunds = self.filtered(lambda rec: rec.move_type == 'out_refund')
        if not refunds:
            return
        ledger = self.env['wof.commission.engine']._wof_ledger()
        for entry in ledger.search([('refund_move_id', 'in', refunds.ids)]):
            source = _('أُلغي أثر المرتجع %s') % entry.refund_move_id.name
            if entry.entry_type == 'normal' and entry.state == 'cancelled' and entry.state_before_cancel:
                entry.write({'state': entry.state_before_cancel, 'state_before_cancel': False,
                             'refund_move_id': False, 'source': source})
            elif entry.entry_type == 'reversal' and entry.state == 'approved':
                entry.write({'state': 'cancelled', 'source': source})

    def button_draft(self):
        result = super().button_draft()
        self._wof_commission_undo_refund()
        return result

    def button_cancel(self):
        result = super().button_cancel()
        self._wof_commission_undo_refund()
        return result
