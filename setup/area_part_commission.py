# -*- coding: utf-8 -*-
"""Commission of a part inside a service area, per film, area and template.

A car part may be sold alone and also be part of a service area. Inside an
area whose commission comes «من الأجزاء», each part of each template has its
own setting, independent from the part sold alone:

* method «حسب تهيئة الجزء»: the commission of the part sold alone in this
  film (a percentage of its price becomes an amount); only offered when the
  part is sold alone in the film;
* method «عمولة موحدة» / «لكل حجم»: amounts of this area only;
* distribution «حسب تهيئة الجزء» (the part's own split), «بالتساوي» or
  «حسب نسبة الفني», used when the area splits «كل جزء حسب تهيئته».

The area commission of an order is the sum of the parts of the template the
order uses. An area with its own commission («مستقلة») keeps one amount for
every template; its parts' values then only weigh their shares.
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

METHODS = [('part', 'حسب تهيئة الجزء'), ('fixed', 'عمولة موحدة'), ('by_size', 'لكل حجم')]
SPLITS = [('part', 'حسب تهيئة الجزء'), ('equal', 'بالتساوي'), ('by_technician_ratio', 'حسب نسبة الفني')]


class WofFilmAreaPartCommission(models.Model):
    _name = 'wof.film.area.part.commission'
    _description = 'عمولة جزء داخل منطقة خدمة'
    _order = 'template_id, sequence, id'

    area_line_id = fields.Many2one('wof.film.parts.lines', string='منطقة الخدمة في الفيلم', required=True,
                                   ondelete='cascade', index=True)
    header_id = fields.Many2one(related='area_line_id.header_id', store=True, string='الفيلم/الخدمة')
    template_id = fields.Many2one('wof.service.area.template', string='النموذج', required=True,
                                  ondelete='cascade', index=True)
    part_id = fields.Many2one('wof.car.parts', string='الجزء', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    method = fields.Selection(METHODS, string='الطريقة', required=True, default='fixed')
    distribution = fields.Selection(SPLITS, string='التوزيع بين الفنيين', required=True, default='equal')
    value_ids = fields.One2many('wof.film.area.part.commission.value', 'config_id', string='القيم')

    _sql_constraints = [
        ('area_template_part_unique', 'unique(area_line_id, template_id, part_id)',
         'لكل جزء في نموذج منطقة الخدمة إعداد عمولة واحد في الفيلم.'),
    ]


class WofFilmAreaPartCommissionValue(models.Model):
    _name = 'wof.film.area.part.commission.value'
    _description = 'قيمة عمولة جزء داخل منطقة خدمة'

    config_id = fields.Many2one('wof.film.area.part.commission', required=True, ondelete='cascade', index=True)
    car_size_id = fields.Many2one('wof.car.size', string='الحجم', ondelete='cascade',
                                  help='فارغ: القيمة الموحدة لكل الأحجام.')
    amount = fields.Float(string='العمولة', required=True)

    _sql_constraints = [
        ('config_size_unique', 'unique(config_id, car_size_id)', 'قيمة واحدة لكل حجم.'),
    ]

    @api.constrains('amount')
    def _check_amount(self):
        if any(rec.amount < 0 for rec in self):
            raise ValidationError(_('العمولة لا يمكن أن تكون سالبة.'))


class WofFilmAreaCommission(models.Model):
    _inherit = 'wof.film.category'

    @api.model
    def _wof_area_templates(self, area):
        """Active templates of a service area, default first."""
        if not area or area.part_type != 'service_area':
            return self.env['wof.service.area.template']
        return area.template_ids.filtered('active').sorted(lambda rec: (not rec.is_default, rec.sequence, rec.id))

    def _wof_standalone_line(self, part):
        """The film line selling this part alone, if any."""
        self.ensure_one()
        return self.film_part_line_ids.filtered(lambda line: line.car_part_id == part and line.part_selected)[:1]

    @api.model
    def _wof_size_value(self, records, size, amount_field):
        """Value of ``records`` (one per size, or a general one) for ``size``; None when missing."""
        found = records.filtered(lambda rec: rec.car_size_id == size)[:1] if size else records.browse()
        if not found:
            found = records.filtered(lambda rec: not rec.car_size_id)[:1]
        return found[amount_field] if found else None

    def _wof_line_commission_amount(self, line, size):
        """Commission amount of a film line for a size; a percentage uses the line price. None if missing."""
        self.ensure_one()
        value = self._wof_size_value(line.commission_line_ids, size, 'commission')
        if value is None:
            return None
        if line.commission_value_type == 'percent':
            price = line.price_line_ids.filtered(lambda rec: rec.car_size_id == size)[:1] if size \
                else line.price_line_ids.browse()
            if not price:
                price = line.price_line_ids.filtered(lambda rec: not rec.car_size_id)[:1]
            if not price:
                return None
            return (0.0 if price.free_part else price.part_price) * value / 100.0
        return value

    def _wof_area_config(self, area_line, template, part):
        self.ensure_one()
        return self.env['wof.film.area.part.commission'].search([
            ('area_line_id', '=', area_line.id), ('template_id', '=', template.id), ('part_id', '=', part.id),
        ], limit=1)

    def _wof_area_part_method(self, config, part):
        """Effective method: a part not sold alone cannot follow «حسب تهيئة الجزء»."""
        method = config.method if config else 'part'
        if method == 'part' and not self._wof_standalone_line(part):
            return 'missing'
        return method

    def _wof_area_part_value(self, area_line, template, part, size, config=None):
        """Commission of ``part`` inside the area for ``size``; None when not set."""
        self.ensure_one()
        config = config if config is not None else self._wof_area_config(area_line, template, part)
        method = self._wof_area_part_method(config, part)
        if method == 'part':
            return self._wof_line_commission_amount(self._wof_standalone_line(part), size)
        if method == 'missing':
            return None
        if method == 'by_size':
            if not size:
                return None
            found = config.value_ids.filtered(lambda rec: rec.car_size_id == size)[:1]
            return found.amount if found else None
        found = config.value_ids.filtered(lambda rec: not rec.car_size_id)[:1]
        return found.amount if found else None

    def _wof_area_part_rule(self, area_line, template, part, config=None):
        """How the part splits its commission between its technicians inside the area."""
        self.ensure_one()
        config = config if config is not None else self._wof_area_config(area_line, template, part)
        rule = config.distribution if config else 'part'
        if rule == 'part':
            line = self._wof_standalone_line(part)
            rule = line.technician_commission_distribution if line else 'equal'
        return rule if rule in ('equal', 'by_technician_ratio') else 'equal'

    def _wof_area_total(self, area_line, template, size):
        """Area commission «من الأجزاء» for a template and size; None if a part is missing."""
        self.ensure_one()
        if not template or not template.component_ids:
            return None
        total = 0.0
        for part in template.component_ids:
            value = self._wof_area_part_value(area_line, template, part, size)
            if value is None:
                return None
            total += value
        return total

    def _wof_area_complete(self, area_line, sizes):
        """Every part of every template has a value for every size."""
        self.ensure_one()
        templates = self._wof_area_templates(area_line.car_part_id)
        if not templates:
            return False
        targets = list(sizes) or [False]
        return all(self._wof_area_total(area_line, template, size) is not None
                   for template in templates for size in targets)
