from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class CarPartsWizard(models.TransientModel):
    _name = 'wof.car.parts.wizard'
    _description = 'Car Parts Wizard'

    # ================= STEPS =================
    step = fields.Selection([
        ('step1', 'البيانات'),
        ('step2', 'الإعدادات'),
        ('step3', 'الأسعار'),
        ('step4', 'المقاسات'),
        ('review', 'مراجعة'),
    ], default='step1')

    progress = fields.Integer(compute="_compute_progress")

    # ================= MAIN =================
    name = fields.Char(required=True)
    service_type = fields.Many2one('wo.services.types')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    commission = fields.Float()
    default_qty = fields.Float()

    # ================= O2M =================
    line_ids = fields.One2many('wof.car.parts.wizard.line', 'wizard_id')
    price_line_ids = fields.One2many('wof.car.parts.wizard.price', 'wizard_id')
    size_line_ids = fields.One2many('wof.car.parts.wizard.size', 'wizard_id')

    # ================= DRAFT =================
    is_draft = fields.Boolean(default=True)

    # ================= PROGRESS =================
    @api.depends('step')
    def _compute_progress(self):
        mapping = {
            'step1': 20,
            'step2': 40,
            'step3': 60,
            'step4': 80,
            'review': 100
        }
        for rec in self:
            rec.progress = mapping.get(rec.step, 0)

    # ================= AUTO FILL =================
    @api.onchange('service_type')
    def _onchange_service_type(self):
        if self.service_type:
            self.commission = 10  # مثال
            self.default_qty = 1

    # ================= VALIDATION =================
    def _validate_step(self):
        for rec in self:
            if rec.step == 'step1' and not rec.name:
                raise ValidationError("الاسم مطلوب")

            if rec.step == 'step3' and not rec.price_line_ids:
                raise ValidationError("أدخل على الأقل سطر سعر")

    # ================= NAVIGATION =================
    def action_next(self):
        self._validate_step()

        for rec in self:
            if rec.step == 'step1':
                rec.step = 'step2'
            elif rec.step == 'step2':
                rec.step = 'step3'
            elif rec.step == 'step3':
                rec.step = 'step4'
            elif rec.step == 'step4':
                rec.step = 'review'

    def action_prev(self):
        for rec in self:
            if rec.step == 'step2':
                rec.step = 'step1'
            elif rec.step == 'step3':
                rec.step = 'step2'
            elif rec.step == 'step4':
                rec.step = 'step3'
            elif rec.step == 'review':
                rec.step = 'step4'

    # ================= CREATE =================
    def action_create_record(self):
        part = self.env['wo.car.parts'].create({
            'name': self.name,
            'service_type': self.service_type.id,
            'company_id': self.company_id.id,
            'commission': self.commission,
            'default_qty': self.default_qty,
        })

        # Lines
        for line in self.line_ids:
            self.env['wof.car.parts.lines'].create({
                'name': line.name,
                'header_id': part.id,
            })

        # Prices
        for line in self.price_line_ids:
            self.env['wof.car.parts.com.lines'].create({
                'header_id': part.id,
                'part_price': line.part_price,
                'service_type': line.service_type.id,
            })

        # Sizes
        for line in self.size_line_ids:
            self.env['wof.car.parts.size.lines'].create({
                'header_id': part.id,
                'default_qty': line.default_qty,
                'min_qty': line.min_qty,
                'max_qty': line.max_qty,
            })

        self.is_draft = False

class CarPartsWizardLine(models.TransientModel):
    _name = 'wof.car.parts.wizard.line'

    wizard_id = fields.Many2one('wof.car.parts.wizard')
    name = fields.Char(required=True)

class CarPartsWizardSize(models.TransientModel):
    _name = 'wof.car.parts.wizard.size'

    wizard_id = fields.Many2one('wof.car.parts.wizard')
    default_qty = fields.Float()
    min_qty = fields.Float()
    max_qty = fields.Float()


class CarPartsWizardPrice(models.TransientModel):
    _name = 'wof.car.parts.wizard.price'

    wizard_id = fields.Many2one('wof.car.parts.wizard')
    service_type = fields.Many2one('wo.services.types')
    part_price = fields.Float()