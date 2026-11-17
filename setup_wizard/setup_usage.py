# -*- coding: utf-8 -*-
"""The setup screen respects what the films and the orders already use.

* Activities, sizes and tint shades show where they are used; a used one
  cannot be renamed, and cannot be switched off while open orders or active
  films still need it (the same rules as the master records, see
  setup/usage_guard.py).
* Once the system is active, a change on these steps reaches the master
  records at once: before, it waited for an activation that never came back.
* The tint numbering method cannot change once a shade is used.
"""

from odoo import _, api, models
from odoo.exceptions import ValidationError

MASTER_OPS = ('activity', 'activity_add', 'size', 'size_add', 'shade')


class WofProfileUsage(models.Model):
    _inherit = 'wof.company.profile'

    # ------------------------------------------------------------ mapping
    def _wof_activity_master(self, line):
        Activity = self.env['wof.service.type'].with_context(active_test=False)
        code = 'ACT-SETUP-TINT' if line.activity_type == 'tint' else 'ACT-SETUP-GEN-%s' % line.id
        return Activity.search([('code', '=', code)], limit=1) \
            or Activity.search([('name', '=', line.name)], limit=1)

    def _wof_size_master(self, line):
        return self.env['wof.car.size'].with_context(active_test=False).search([('code', '=', line.code)], limit=1)

    @api.model
    def _wof_usage_entry(self, model, info):
        used = model._wof_is_used(info)
        return {
            'used': used,
            'usage': model._wof_usage_describe(info) if used else '',
            'off_block': (model._wof_archive_block(info) or '') if used else '',
        }

    def _wof_lines_usage(self):
        """{('activity'|'size'|'shade', line id): {'used', 'usage', 'off_block'}}."""
        self.ensure_one()
        result = {}
        Activity, Size, Degree = self.env['wof.service.type'], self.env['wof.car.size'], self.env['wof.tint.degree']
        masters = {line.id: self._wof_activity_master(line) for line in self.activity_line_ids}
        records = Activity.browse([rec.id for rec in masters.values() if rec])
        usage = records._wof_usage_map() if records else {}
        for line_id, master in masters.items():
            result[('activity', line_id)] = self._wof_usage_entry(Activity, usage.get(master.id, {}) if master else {})
        masters = {line.id: self._wof_size_master(line) for line in self.size_line_ids}
        records = Size.browse([rec.id for rec in masters.values() if rec])
        usage = records._wof_usage_map() if records else {}
        for line_id, master in masters.items():
            result[('size', line_id)] = self._wof_usage_entry(Size, usage.get(master.id, {}) if master else {})
        shades = Degree._wof_shade_usage([(line.code, line.value) for line in self.tint_shade_line_ids])
        for line in self.tint_shade_line_ids:
            result[('shade', line.id)] = self._wof_usage_entry(Degree, shades.get(line.code, {}))
        return result

    # ------------------------------------------------------------ snapshot
    def _wof_flow_snapshot(self):
        data = super()._wof_flow_snapshot()
        usage = self._wof_lines_usage()
        empty = {'used': False, 'usage': '', 'off_block': ''}
        for key, rows in (('activity', data['activities']), ('size', data['sizes']), ('shade', data['tint']['shades'])):
            for row in rows:
                row.update(usage.get((key, row['id']), empty))
        data['tint']['method_locked'] = data['tint']['locked'] or any(row['used'] for row in data['tint']['shades'])
        films = self.env['wof.film.category'].with_context(active_test=False).search_count([])
        data['film_count'] = films
        return data

    # ------------------------------------------------------------ apply
    def wof_flow_apply(self, op, payload=None):
        data = super().wof_flow_apply(op, payload)
        if op in MASTER_OPS and self.state == 'ready':
            issues = self._readiness_issues()
            if issues:
                raise ValidationError(_('لا يمكن حفظ هذا التغيير والنظام مفعّل: %s.') % issues[0]['message'])
            # The system is live: the change reaches the master records now.
            self._apply_master_setup()
            data = self._wof_flow_snapshot()
        return data

    def _set_tint_numbering_method(self, method):
        if method != self.tint_numbering_method and self.tint_shade_line_ids:
            usage = self.env['wof.tint.degree']._wof_shade_usage(
                [(line.code, line.value) for line in self.tint_shade_line_ids])
            if any(self.env['wof.tint.degree']._wof_is_used(info) for info in usage.values()):
                raise ValidationError(_(
                    'درجات اللون الحالية مستخدمة في الأفلام أو الأوامر، لذلك لا يمكن تغيير طريقة الترقيم.'))
        return super()._set_tint_numbering_method(method)


class WofSetupLineGuard(models.AbstractModel):
    _name = 'wof.setup.line.guard'
    _description = 'حماية بنود التهيئة المستخدمة'

    _wof_kind = ''
    _wof_name_field = 'name'
    _wof_label = ''

    def _wof_guard(self, vals, unlink=False):
        if self.env.context.get('wof_usage_skip'):
            return
        renaming = self._wof_name_field in vals
        stopping = 'selected' in vals and not vals['selected']
        if not (renaming or stopping or unlink):
            return
        for profile in self.mapped('profile_id'):
            usage = profile._wof_lines_usage()
            for line in self.filtered(lambda rec: rec.profile_id == profile):
                info = usage.get((self._wof_kind, line.id)) or {}
                if not info.get('used'):
                    continue
                current = line[self._wof_name_field] or ''
                if renaming and (vals[self._wof_name_field] or '').strip() != current.strip():
                    raise ValidationError(_(
                        '%(what)s «%(name)s» مستخدم (%(usage)s)، لذلك لا يمكن تغيير اسمه.\n'
                        'إن احتجت، أضف %(what)s جديدًا وأوقف هذا؛ تبقى الأوامر القديمة كما هي.'
                    ) % {'what': self._wof_label, 'name': current, 'usage': info['usage']})
                if stopping and line.selected and info.get('off_block'):
                    raise ValidationError(_('لا يمكن إيقاف %(what)s «%(name)s»: %(reason)s') % {
                        'what': self._wof_label, 'name': current, 'reason': info['off_block']})
                if unlink:
                    raise ValidationError(_('لا يمكن حذف %(what)s «%(name)s» لأنه مستخدم (%(usage)s). أوقفه بدل الحذف.') % {
                        'what': self._wof_label, 'name': current, 'usage': info['usage']})


class WofSetupActivityLineGuard(models.Model):
    _name = 'wof.setup.activity.line'
    _inherit = ['wof.setup.activity.line', 'wof.setup.line.guard']
    _wof_kind = 'activity'
    _wof_label = 'النشاط'

    def write(self, vals):
        self._wof_guard(vals)
        return super().write(vals)

    def unlink(self):
        self._wof_guard({}, unlink=True)
        return super().unlink()


class WofSetupSizeLineGuard(models.Model):
    _name = 'wof.setup.size.line'
    _inherit = ['wof.setup.size.line', 'wof.setup.line.guard']
    _wof_kind = 'size'
    _wof_label = 'حجم السيارة'

    def write(self, vals):
        self._wof_guard(vals)
        return super().write(vals)

    def unlink(self):
        self._wof_guard({}, unlink=True)
        return super().unlink()


class WofSetupShadeLineGuard(models.Model):
    _name = 'wof.setup.tint.shade.line'
    _inherit = ['wof.setup.tint.shade.line', 'wof.setup.line.guard']
    _wof_kind = 'shade'
    _wof_name_field = 'value'
    _wof_label = 'درجة اللون'

    def write(self, vals):
        self._wof_guard(vals)
        return super().write(vals)

    def unlink(self):
        self._wof_guard({}, unlink=True)
        return super().unlink()
