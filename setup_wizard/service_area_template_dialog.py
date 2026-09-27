# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class WofFilmSetupComponentCreateDialog(models.TransientModel):
    _inherit = 'wof.film.setup.component.create.dialog'

    template_line_ids = fields.One2many('wof.film.setup.service.area.template.line', 'dialog_id', string='نماذج مكونات منطقة الخدمة')

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records.filtered(lambda rec: rec.expected_type == 'service_area'):
            record._load_template_lines()
        return records

    def _load_template_lines(self):
        self.ensure_one()
        if self.template_line_ids:
            return
        part = self.edit_part_id
        if part:
            part.ensure_service_area_templates()
            for template in part.template_ids.filtered('active').sorted(lambda rec: (rec.sequence, rec.id)):
                self.env['wof.film.setup.service.area.template.line'].create({
                    'dialog_id': self.id, 'template_id': template.id, 'name': template.name,
                    'sequence': template.sequence, 'is_default': template.is_default,
                    'component_ids': [(6, 0, template.component_ids.ids)],
                })
        if not self.template_line_ids:
            self.env['wof.film.setup.service.area.template.line'].create({
                'dialog_id': self.id, 'name': _('النموذج الأساسي'), 'sequence': 10,
                'is_default': True, 'component_ids': [(6, 0, self.service_area_part_ids.ids)],
            })

    def _validate_template_lines(self):
        self.ensure_one()
        if self.expected_type != 'service_area':
            return
        lines = self.template_line_ids
        if not lines:
            raise ValidationError(_('أضف نموذج مكونات واحدًا على الأقل لمنطقة الخدمة.'))
        if lines.filtered(lambda line: not (line.name or '').strip()):
            raise ValidationError(_('أدخل اسمًا لكل نموذج مكونات.'))
        if lines.filtered(lambda line: not line.component_ids):
            raise ValidationError(_('كل نموذج يجب أن يحتوي على مكوّن واحد على الأقل.'))
        defaults = lines.filtered('is_default')
        if len(defaults) != 1:
            raise ValidationError(_('حدد نموذجًا افتراضيًا واحدًا فقط لمنطقة الخدمة.'))
        names = [(line.name or '').strip().lower() for line in lines]
        if len(names) != len(set(names)):
            raise ValidationError(_('لا يمكن تكرار اسم النموذج داخل منطقة الخدمة.'))
        wrong = lines.mapped('component_ids').filtered(lambda part: part.company_id != self.company_id or part.part_type != 'car_part')
        if wrong:
            raise ValidationError(_('مكونات النماذج يجب أن تكون أجزاء سيارة من نفس الشركة.'))
        self.service_area_part_ids = [(6, 0, defaults.component_ids.ids)]

    def _sync_persistent_templates(self, part):
        self.ensure_one()
        if self.expected_type != 'service_area':
            return
        Template = self.env['wof.service.area.template'].with_context(active_test=False)
        keep_ids = []
        default_line = self.template_line_ids.filtered('is_default')[:1]
        for line in self.template_line_ids.sorted(lambda rec: (rec.sequence, rec.id)):
            vals = {'name': (line.name or '').strip(), 'sequence': line.sequence, 'service_area_id': part.id,
                    'component_ids': [(6, 0, line.component_ids.ids)], 'active': True, 'is_default': line == default_line}
            template = line.template_id
            if template and template.service_area_id == part:
                template.write(vals)
            else:
                template = Template.create(vals)
            keep_ids.append(template.id)
        obsolete = Template.search([('service_area_id', '=', part.id), ('id', 'not in', keep_ids), ('active', '=', True)])
        if obsolete:
            obsolete.write({'active': False, 'is_default': False})
        part.service_area_part_ids = [(6, 0, default_line.component_ids.ids)]

    def action_save_changes(self):
        self._validate_template_lines()
        part = self.edit_part_id
        result = super().action_save_changes()
        if part and self.expected_type == 'service_area':
            self._sync_persistent_templates(part)
            if self.edit_line_id:
                self.wizard_id._prepare_component_lines()
        return result

    def action_create_and_add(self):
        self._validate_template_lines()
        result = super().action_create_and_add()
        if self.expected_type == 'service_area':
            part = self.env['wof.car.parts'].search([
                ('company_id', '=', self.company_id.id), ('name', '=ilike', (self.name or '').strip()),
                ('part_type', '=', 'service_area')], order='id desc', limit=1)
            if part:
                self._sync_persistent_templates(part)
                self.wizard_id._prepare_component_lines()
        return result


class WofFilmSetupServiceAreaTemplateLine(models.TransientModel):
    _name = 'wof.film.setup.service.area.template.line'
    _description = 'نموذج مكونات منطقة خدمة داخل معالج الفيلم'
    _order = 'sequence, id'

    dialog_id = fields.Many2one('wof.film.setup.component.create.dialog', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='dialog_id.company_id', readonly=True)
    template_id = fields.Many2one('wof.service.area.template', readonly=True, ondelete='set null')
    sequence = fields.Integer(string='الترتيب', default=10)
    name = fields.Char(string='اسم النموذج', required=True)
    is_default = fields.Boolean(string='افتراضي')
    component_ids = fields.Many2many(
        'wof.car.parts', 'wof_film_setup_area_template_line_part_rel', 'line_id', 'part_id', string='المكونات',
        domain="[('company_id', '=', company_id), ('part_type', '=', 'car_part'), ('active', '=', True)]")

    @api.onchange('is_default')
    def _onchange_is_default(self):
        if self.is_default and self.dialog_id:
            for line in self.dialog_id.template_line_ids - self:
                line.is_default = False


class WofFilmSetupWizardTemplateTree(models.TransientModel):
    _inherit = 'wof.film.setup.wizard'

    def _template_tree_values(self, area, parent_sequence):
        area.ensure_service_area_templates()
        vals = []
        offset = 1
        templates = area.template_ids.filtered('active').sorted(lambda rec: (rec.sequence, rec.id))
        for template in templates:
            vals.append({
                'wizard_id': self.id, 'sequence': parent_sequence + offset,
                'car_part_id': area.id, 'selected': True, 'is_child': True,
                'parent_master_id': area.id, 'node_type': 'template',
                'template_id': template.id,
            })
            offset += 1
            for child in template.component_ids.sorted(lambda rec: (rec.priority_part, rec.name or '', rec.id)):
                vals.append({
                    'wizard_id': self.id, 'sequence': parent_sequence + offset,
                    'car_part_id': child.id, 'selected': True, 'is_child': True,
                    'parent_master_id': area.id, 'node_type': 'template_part',
                    'parent_template_id': template.id,
                })
                offset += 1
        return vals

    def _prepare_component_lines(self):
        self.ensure_one()
        self.component_line_ids.unlink()
        if not self.film_id:
            return
        existing_part_ids = set(self.film_id.film_part_line_ids.filtered('part_selected').mapped('car_part_id').ids)
        masters = self.env['wof.car.parts'].with_context(active_test=False).search([
            ('company_id', '=', self.company_id.id), ('active', '=', True)], order='priority_part, name, id')
        vals, seq = [], 10
        for part in masters:
            if part.id not in existing_part_ids:
                continue
            vals.append({'wizard_id': self.id, 'sequence': seq, 'car_part_id': part.id,
                         'selected': True, 'is_child': False, 'node_type': 'component'})
            if part.part_type == 'service_area':
                vals.extend(self._template_tree_values(part, seq))
            seq += 100
        if vals:
            self.env['wof.film.setup.component.line'].create(vals)

    def _append_component_master(self, part):
        self.ensure_one()
        part.ensure_one()
        if part.company_id != self.company_id or not part.active:
            raise ValidationError(_('المكوّن المحدد غير متاح لهذه الشركة.'))
        existing = self.component_line_ids.filtered(lambda line: not line.is_child and line.car_part_id == part)[:1]
        if existing:
            existing.selected = True
            return existing
        max_seq = max(self.component_line_ids.mapped('sequence') or [0])
        parent = self.env['wof.film.setup.component.line'].create({
            'wizard_id': self.id, 'sequence': max_seq + 100, 'car_part_id': part.id,
            'selected': True, 'is_child': False, 'node_type': 'component'})
        if part.part_type == 'service_area':
            values = self._template_tree_values(part, parent.sequence)
            if values:
                self.env['wof.film.setup.component.line'].create(values)
        return parent

    @api.depends('component_line_ids.selected', 'component_line_ids.part_type', 'component_line_ids.is_child', 'component_line_ids.node_type')
    def _compute_component_summary(self):
        for wizard in self:
            top = wizard.component_line_ids.filtered(lambda line: not line.is_child and line.selected)
            wizard.selected_component_count = len(top)
            wizard.service_area_count = len(top.filtered(lambda line: line.part_type == 'service_area'))
            wizard.structural_part_count = len(wizard.component_line_ids.filtered(
                lambda line: line.node_type == 'template_part' and line.parent_selected))


class WofFilmSetupComponentLineTemplateTree(models.TransientModel):
    _inherit = 'wof.film.setup.component.line'

    node_type = fields.Selection([
        ('component', 'مكوّن'), ('template', 'نموذج'), ('template_part', 'مكوّن نموذج')],
        default='component', readonly=True)
    template_id = fields.Many2one('wof.service.area.template', string='النموذج', readonly=True)
    parent_template_id = fields.Many2one('wof.service.area.template', string='النموذج الأب', readonly=True)
    template_name = fields.Char(related='template_id.name', readonly=True)
    template_is_default = fields.Boolean(related='template_id.is_default', readonly=True)
    template_component_count = fields.Integer(related='template_id.component_ids', readonly=True)
    template_expanded = fields.Boolean(string='إظهار مكونات النموذج', default=False)
    parent_template_expanded = fields.Boolean(compute='_compute_parent_template_expanded')

    @api.depends('wizard_id.component_line_ids.template_expanded', 'parent_template_id')
    def _compute_parent_template_expanded(self):
        for line in self:
            if line.node_type != 'template_part' or not line.parent_template_id:
                line.parent_template_expanded = False
                continue
            parent = line.wizard_id.component_line_ids.filtered(
                lambda rec: rec.node_type == 'template' and rec.template_id == line.parent_template_id)[:1]
            line.parent_template_expanded = bool(parent and parent.template_expanded)

    @api.depends('car_part_id.service_area_part_ids', 'car_part_id.template_ids.active')
    def _compute_child_count(self):
        for line in self:
            if line.node_type == 'template':
                line.child_count = len(line.template_id.component_ids)
                line.child_names = '، '.join(line.template_id.component_ids.mapped('name'))
            elif line.part_type == 'service_area' and not line.is_child:
                active_templates = line.car_part_id.template_ids.filtered('active')
                line.child_count = len(active_templates)
                line.child_names = '، '.join(active_templates.mapped('name'))
            else:
                line.child_count = 0
                line.child_names = ''

    def action_toggle_template(self):
        self.ensure_one()
        if self.node_type == 'template':
            self.template_expanded = not self.template_expanded
        return self.wizard_id._dialog_action()
