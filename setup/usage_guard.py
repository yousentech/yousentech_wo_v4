# -*- coding: utf-8 -*-
"""Master data that the films and the orders depend on stays coherent.

Once a size, an activity, a tint shade, a component or an extra option is used
(in a film setup or in an installation order) its identity is locked: renaming
it would rewrite the history of old orders, and removing it would break the
films that price it. The safe path is always offered instead: add a new record
and stop (archive) the old one. Stopping is refused while open orders or
active films still need the record.

Usage is read by SQL so the company switcher and record rules never hide a use.
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

CLOSED_STATES = ('delivered', 'cancelled')
USAGE_KEYS = ('films', 'active_films', 'orders', 'open_orders', 'vehicles', 'areas', 'components', 'other')


def _empty():
    return dict.fromkeys(USAGE_KEYS, 0)


class WofUsageMixin(models.AbstractModel):
    _name = 'wof.usage.mixin'
    _description = 'حماية البيانات الأساسية المستخدمة'

    # Identity fields locked once the record is used.
    _wof_guard_fields = ()
    # Article for messages, e.g. «حجم السيارة».
    _wof_guard_label = ''

    wof_in_use = fields.Boolean(string='مستخدم', compute='_compute_wof_usage')
    wof_locked = fields.Boolean(string='مقفل', compute='_compute_wof_usage')
    wof_usage_text = fields.Char(string='الاستخدام', compute='_compute_wof_usage')

    def _compute_wof_usage(self):
        usage = self._wof_usage_map() if self.ids else {}
        for record in self:
            info = usage.get(record.id) or _empty()
            record.wof_in_use = self._wof_is_used(info)
            record.wof_locked = set(self._wof_guard_fields) <= self._wof_locked_fields(info)
            record.wof_usage_text = self._wof_usage_describe(info) if record.wof_in_use else False

    def _wof_locked_fields(self, info):
        """Identity fields that this usage locks (all of them once used)."""
        return set(self._wof_guard_fields) if self._wof_is_used(info) else set()

    # ------------------------------------------------------------- usage
    def _wof_usage_map(self):
        """{id: usage dict}; overridden per model."""
        return {}

    def _wof_sql_counts(self, query, params, usage, keys):
        """Run ``query`` (first column: id, then one column per key) into ``usage``."""
        self.env.cr.execute(query, params)
        for row in self.env.cr.fetchall():
            info = usage.setdefault(row[0], _empty())
            for key, value in zip(keys, row[1:]):
                info[key] += value or 0
        return usage

    def _wof_flush_usage_tables(self):
        for model in ('wof.installation.order', 'wof.installation.order.line', 'wof.installation.order.line.part',
                      'wof.film.category', 'wof.film.category.lines', 'wof.film.parts.lines',
                      'wof.film.parts.price.lines', 'wof.film.parts.commission.lines', 'wof.vehicle',
                      'wof.car.part.stock.qty', 'wof.service.area.template', 'wof.car.parts'):
            if model in self.env:
                self.env[model].flush_model()

    @api.model
    def _wof_is_used(self, info):
        return any(info.get(key) for key in ('films', 'orders', 'vehicles', 'areas', 'components', 'other'))

    @api.model
    def _wof_usage_describe(self, info):
        parts = []
        if info.get('films'):
            parts.append(_('%s فيلم/خدمة') % info['films'])
        if info.get('orders'):
            text = _('%s أمر تركيب') % info['orders']
            if info.get('open_orders'):
                text += _(' (%s مفتوح)') % info['open_orders']
            parts.append(text)
        if info.get('vehicles'):
            parts.append(_('%s سيارة عميل') % info['vehicles'])
        if info.get('areas'):
            parts.append(_('%s منطقة خدمة') % info['areas'])
        if info.get('components'):
            parts.append(_('%s مكوّن') % info['components'])
        if info.get('other'):
            parts.append(_('%s إعداد مخزون') % info['other'])
        return ' · '.join(parts)

    def _wof_archive_block(self, info):
        """Reason why this used record cannot be stopped now, or False."""
        if info.get('open_orders'):
            return _('عليه %s أمر تركيب مفتوح؛ أكمل الأوامر أو ألغها أولًا.') % info['open_orders']
        return False

    def _wof_display(self):
        self.ensure_one()
        return self.display_name

    @api.model
    def _wof_same_value(self, record, name, value):
        current = record[name]
        field = record._fields[name]
        if field.type == 'many2one':
            new_id = value.id if isinstance(value, models.BaseModel) else (value or False)
            return current.id == new_id
        if field.type in ('char', 'text'):
            return (current or '').strip() == (value or '').strip()
        return current == value

    # ------------------------------------------------------------ guards
    def write(self, vals):
        if self.env.context.get('wof_usage_skip') or not self:
            return super().write(vals)
        changing = [name for name in self._wof_guard_fields if name in vals]
        archiving = 'active' in vals and not vals['active']
        if changing or archiving:
            usage = self._wof_usage_map()
            for record in self:
                info = usage.get(record.id) or _empty()
                if not self._wof_is_used(info):
                    continue
                locked = record._wof_locked_fields(info)
                blocked = [name for name in changing
                           if name in locked and not self._wof_same_value(record, name, vals[name])]
                if blocked:
                    labels = '، '.join(record._fields[name].string for name in blocked)
                    raise ValidationError(_(
                        '%(what)s «%(name)s» مستخدم (%(usage)s)، لذلك لا يمكن تغيير: %(fields)s.\n'
                        'إن احتجت، أضف %(what)s جديدًا وأوقف هذا؛ تبقى الأوامر القديمة كما هي.'
                    ) % {'what': self._wof_guard_label, 'name': record._wof_display(),
                         'usage': self._wof_usage_describe(info), 'fields': labels})
                if archiving and record.active:
                    reason = record._wof_archive_block(info)
                    if reason:
                        raise ValidationError(_('لا يمكن إيقاف %(what)s «%(name)s»: %(reason)s') % {
                            'what': self._wof_guard_label, 'name': record._wof_display(), 'reason': reason})
        return super().write(vals)

    def unlink(self):
        if not self.env.context.get('wof_usage_skip') and self:
            usage = self._wof_usage_map()
            for record in self:
                info = usage.get(record.id) or _empty()
                if self._wof_is_used(info):
                    raise ValidationError(_(
                        'لا يمكن حذف %(what)s «%(name)s» لأنه مستخدم (%(usage)s). أوقفه (أرشفة) بدل الحذف.'
                    ) % {'what': self._wof_guard_label, 'name': record._wof_display(),
                         'usage': self._wof_usage_describe(info)})
        return super().unlink()


class WofCarSizeUsage(models.Model):
    _name = 'wof.car.size'
    _inherit = ['wof.car.size', 'wof.usage.mixin']
    _wof_guard_fields = ('name', 'code')
    _wof_guard_label = 'حجم السيارة'

    def _wof_usage_map(self):
        ids = list(self.ids)
        usage = {}
        if not ids:
            return usage
        self._wof_flush_usage_tables()
        self._wof_sql_counts("""
            SELECT car_size_id, count(*), count(*) FILTER (WHERE state NOT IN %s)
              FROM wof_installation_order WHERE car_size_id = ANY(%s) GROUP BY car_size_id
        """, (CLOSED_STATES, ids), usage, ('orders', 'open_orders'))
        self._wof_sql_counts("""
            SELECT u.size_id, count(DISTINCT u.film_id), count(DISTINCT u.film_id) FILTER (WHERE f.active)
              FROM (SELECT p.car_size_id AS size_id, l.header_id AS film_id
                      FROM wof_film_parts_price_lines p JOIN wof_film_parts_lines l ON l.id = p.part_line_id
                    UNION ALL
                    SELECT c.car_size_id, l.header_id
                      FROM wof_film_parts_commission_lines c JOIN wof_film_parts_lines l ON l.id = c.part_line_id
                    UNION ALL
                    SELECT size_id, film_id FROM wof_film_category_car_size_rel) u
              JOIN wof_film_category f ON f.id = u.film_id
             WHERE u.size_id = ANY(%s) GROUP BY u.size_id
        """, (ids,), usage, ('films', 'active_films'))
        self._wof_sql_counts(
            "SELECT car_size_id, count(*) FROM wof_vehicle WHERE car_size_id = ANY(%s) GROUP BY car_size_id",
            (ids,), usage, ('vehicles',))
        self._wof_sql_counts(
            "SELECT car_size_id, count(*) FROM wof_car_part_stock_qty WHERE car_size_id = ANY(%s) GROUP BY car_size_id",
            (ids,), usage, ('other',))
        return usage


class WofServiceTypeUsage(models.Model):
    _name = 'wof.service.type'
    _inherit = ['wof.service.type', 'wof.usage.mixin']
    _wof_guard_fields = ('name', 'code', 'service_options')
    _wof_guard_label = 'النشاط'

    def _wof_usage_map(self):
        ids = list(self.ids)
        usage = {}
        if not ids:
            return usage
        self._wof_flush_usage_tables()
        self._wof_sql_counts("""
            SELECT service_type_id, count(*), count(*) FILTER (WHERE active)
              FROM wof_film_category WHERE service_type_id = ANY(%s) GROUP BY service_type_id
        """, (ids,), usage, ('films', 'active_films'))
        self._wof_sql_counts("""
            SELECT l.service_type_id, count(DISTINCT l.order_id),
                   count(DISTINCT l.order_id) FILTER (WHERE o.state NOT IN %s)
              FROM wof_installation_order_line l JOIN wof_installation_order o ON o.id = l.order_id
             WHERE l.service_type_id = ANY(%s) GROUP BY l.service_type_id
        """, (CLOSED_STATES, ids), usage, ('orders', 'open_orders'))
        return usage

    def _wof_archive_block(self, info):
        if info.get('active_films'):
            return _('تحته %s فيلم/خدمة مفعّلة. أوقفها من «الأفلام والخدمات» أولًا.') % info['active_films']
        return super()._wof_archive_block(info)


class WofTintDegreeUsage(models.Model):
    _name = 'wof.tint.degree'
    _inherit = ['wof.tint.degree', 'wof.usage.mixin']
    _wof_guard_fields = ('value', 'code')
    _wof_guard_label = 'درجة اللون'

    def _wof_display(self):
        return self.value

    @api.model
    def _wof_shade_usage(self, pairs):
        """Usage of tint shades given as [(code, value)], keyed by code.

        Film grades copy the shade (matched by code, or by name for grades made
        by older versions); orders point at those grades.
        """
        usage = {code: _empty() for code, _value in pairs}
        if not pairs:
            return usage
        by_value = {value: code for code, value in pairs if value}
        codes = [code for code, _value in pairs if code]
        self._wof_flush_usage_tables()
        self.env.cr.execute("""
            SELECT g.id, g.code, g.name, g.header_id, g.active AND f.active
              FROM wof_film_category_lines g JOIN wof_film_category f ON f.id = g.header_id
             WHERE g.code = ANY(%s) OR g.name = ANY(%s)
        """, (codes, list(by_value)))
        grade_code = {}
        films, active_films = {}, {}
        for grade_id, code, name, film_id, active in self.env.cr.fetchall():
            key = code if code in usage else by_value.get(name)
            if not key:
                continue
            grade_code[grade_id] = key
            films.setdefault(key, set()).add(film_id)
            if active:
                active_films.setdefault(key, set()).add(film_id)
        for key in usage:
            usage[key]['films'] = len(films.get(key, ()))
            usage[key]['active_films'] = len(active_films.get(key, ()))
        if grade_code:
            self.env.cr.execute("""
                SELECT u.grade_id, count(DISTINCT u.order_id), count(DISTINCT u.order_id) FILTER (WHERE o.state NOT IN %s)
                  FROM (SELECT film_category_line_id AS grade_id, order_id FROM wof_installation_order_line
                         WHERE film_category_line_id = ANY(%s)
                        UNION ALL
                        SELECT grade_id, order_id FROM wof_installation_order_line_part WHERE grade_id = ANY(%s)) u
                  JOIN wof_installation_order o ON o.id = u.order_id
                 GROUP BY u.grade_id
            """, (CLOSED_STATES, list(grade_code), list(grade_code)))
            for grade_id, orders, open_orders in self.env.cr.fetchall():
                info = usage[grade_code[grade_id]]
                info['orders'] += orders
                info['open_orders'] += open_orders
        return usage

    def _wof_usage_map(self):
        if not self.ids:
            return {}
        by_code = self._wof_shade_usage([(rec.code or 'NO-CODE-%s' % rec.id, rec.value) for rec in self])
        return {rec.id: by_code.get(rec.code or 'NO-CODE-%s' % rec.id) or _empty() for rec in self}

    def _wof_archive_block(self, info):
        if info.get('active_films'):
            return _('تعتمد عليها %s فيلم مفعّل. أزلها من درجات الفيلم أولًا.') % info['active_films']
        return super()._wof_archive_block(info)


class WofCarPartsUsage(models.Model):
    _name = 'wof.car.parts'
    _inherit = ['wof.car.parts', 'wof.usage.mixin']
    _wof_guard_fields = ('name', 'code', 'part_type', 'product_id')
    _wof_guard_label = 'المكوّن'

    def _wof_display(self):
        return self.name

    def _wof_locked_fields(self, info):
        # Old orders show the component as it was: its identity is locked once
        # an order uses it. Films only reference it by id (a rename shows in all
        # of them), but its type defines how they price it.
        if info.get('orders'):
            return set(self._wof_guard_fields)
        if self._wof_is_used(info):
            return {'part_type'}
        return set()

    def _wof_usage_map(self):
        ids = list(self.ids)
        usage = {}
        if not ids:
            return usage
        self._wof_flush_usage_tables()
        self._wof_sql_counts("""
            SELECT l.car_part_id, count(DISTINCT l.header_id),
                   count(DISTINCT l.header_id) FILTER (WHERE f.active AND l.part_selected)
              FROM wof_film_parts_lines l JOIN wof_film_category f ON f.id = l.header_id
             WHERE l.car_part_id = ANY(%s) GROUP BY l.car_part_id
        """, (ids,), usage, ('films', 'active_films'))
        self._wof_sql_counts("""
            SELECT u.part_id, count(DISTINCT u.order_id), count(DISTINCT u.order_id) FILTER (WHERE o.state NOT IN %s)
              FROM (SELECT car_part_id AS part_id, order_id FROM wof_installation_order_line WHERE car_part_id = ANY(%s)
                    UNION ALL
                    SELECT part_id, order_id FROM wof_installation_order_line_part WHERE part_id = ANY(%s)) u
              JOIN wof_installation_order o ON o.id = u.order_id
             GROUP BY u.part_id
        """, (CLOSED_STATES, ids, ids), usage, ('orders', 'open_orders'))
        self._wof_sql_counts("""
            SELECT u.part_id, count(DISTINCT u.area_id)
              FROM (SELECT r.part_id, t.service_area_id AS area_id
                      FROM wof_service_area_template_part_rel r
                      JOIN wof_service_area_template t ON t.id = r.template_id
                    UNION ALL
                    SELECT child_part_id, service_area_id FROM wof_car_parts_service_area_rel) u
             WHERE u.part_id = ANY(%s) GROUP BY u.part_id
        """, (ids,), usage, ('areas',))
        return usage

    def _wof_archive_block(self, info):
        if info.get('active_films'):
            return _('في %s فيلم مفعّل؛ أزله من مكوّنات الفيلم أولًا.') % info['active_films']
        return super()._wof_archive_block(info)


class WofPartOptionUsage(models.Model):
    _name = 'wof.car.part.options'
    _inherit = ['wof.car.part.options', 'wof.usage.mixin']
    _wof_guard_fields = ('code',)
    _wof_guard_label = 'الخيار الإضافي'

    def _wof_display(self):
        return self.name

    def _wof_usage_map(self):
        ids = list(self.ids)
        usage = {}
        if not ids:
            return usage
        self._wof_flush_usage_tables()
        self.env['wof.installation.order.line'].flush_model(['option_ids'])
        self._wof_sql_counts("""
            SELECT r.option_id, count(DISTINCT l.order_id),
                   count(DISTINCT l.order_id) FILTER (WHERE o.state NOT IN %s)
              FROM wof_order_line_option_rel r
              JOIN wof_installation_order_line l ON l.id = r.line_id
              JOIN wof_installation_order o ON o.id = l.order_id
             WHERE r.option_id = ANY(%s) GROUP BY r.option_id
        """, (CLOSED_STATES, ids), usage, ('orders', 'open_orders'))
        self._wof_sql_counts("""
            SELECT wof_car_part_options_id, count(*) FROM wof_car_part_options_wof_car_parts_rel
             WHERE wof_car_part_options_id = ANY(%s) GROUP BY wof_car_part_options_id
        """, (ids,), usage, ('components',))
        return usage

    def _wof_archive_block(self, info):
        return False  # stopping an option keeps it on the orders that chose it
