# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class WofSystemSettings(models.Model):
    _name = 'wof.system.settings'
    _description = 'Car Film System Settings'
    _rec_name = 'name'
    _order = 'company_id'

    name = fields.Char(string='Name', compute='_compute_name', store=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self._default_company_id(),
        index=True,
    )

    # Work Order settings
    enable_work_order = fields.Boolean(string='Enable Work Orders', default=True)
    plate_number_required = fields.Boolean(string='Plate Number Required', default=True)
    chassis_number_required = fields.Boolean(string='Chassis Number Required')
    customer_mobile_required = fields.Boolean(string='Customer Mobile Required', default=True)
    manufacture_year_required = fields.Boolean(string='Manufacture Year Required')
    car_color_required = fields.Boolean(string='Car Color Required')
    car_agency_required = fields.Boolean(string='Agency Required')
    delivery_datetime_required = fields.Boolean(string='Delivery Date/Time Required')
    allow_multiple_technicians = fields.Boolean(string='Allow Multiple Technicians', default=True)
    technician_required = fields.Boolean(string='Technician Required')
    technician_commission_trigger = fields.Selection(
        [
            ('invoice_posted', 'After Invoice Posting'),
            ('work_order_done', 'After Work Order Completion'),
        ],
        string='Technician Commission Eligibility',
        default='work_order_done',
        required=True,
    )

    # Discount settings
    enable_discounts = fields.Boolean(string='Enable Discounts', default=True)
    discount_level = fields.Selection(
        [
            ('total', 'Total Level'),
            ('service', 'Service Level'),
            ('service_detail', 'Service Detail Level'),
        ],
        string='Discount Level',
        default='total',
        required=True,
    )
    allow_package_discount = fields.Boolean(string='Allow Discount in Packages')
    propagate_discount_to_invoice = fields.Boolean(string='Propagate Discount to Invoice')

    # Inventory and films
    enable_film_area_m2 = fields.Boolean(string='Use Film Area in Square Meter')
    enable_roll_consumption_tracking = fields.Boolean(string='Track Film Roll Consumption')
    roll_consumption_method = fields.Selection(
        [
            ('manual', 'Manual'),
            ('car_parts', 'By Car Parts'),
            ('sizes', 'By Sizes'),
        ],
        string='Roll Consumption Method',
        default='manual',
        required=True,
    )
    removal_as_extra_service = fields.Boolean(string='Remove Old Stickers as Extra Service', default=True)

    # Invoice and payment
    create_invoice_after_full_payment = fields.Boolean(string='Create Invoice After Full Payment')
    auto_create_invoice_on_confirm = fields.Boolean(string='Auto Create Invoice on Work Order Confirmation')
    block_delivery_until_full_payment = fields.Boolean(string='Block Delivery Until Full Payment')

    # Reports
    report_car_diagram_image = fields.Binary(string='Car Diagram Image', attachment=True)
    report_car_diagram_filename = fields.Char(string='Car Diagram Filename')
    report_work_order_terms_image = fields.Binary(string='Work Order Terms Image', attachment=True)
    report_work_order_terms_filename = fields.Char(string='Work Order Terms Filename')
    report_warranty_terms_image = fields.Binary(string='Warranty Terms Image', attachment=True)
    report_warranty_terms_filename = fields.Char(string='Warranty Terms Filename')
    report_invoice_terms_image = fields.Binary(string='Invoice Terms Image', attachment=True)
    report_invoice_terms_filename = fields.Char(string='Invoice Terms Filename')
    report_footer_note = fields.Text(string='Work Order Report Footer Note')
    enable_warranty_qr = fields.Boolean(string='Enable Warranty QR', default=True)

    # Main screen UI
    hide_plate_number = fields.Boolean(string='Hide Plate Number')
    hide_chassis_number = fields.Boolean(string='Hide Chassis Number')
    hide_manufacture_year = fields.Boolean(string='Hide Manufacture Year')
    hide_car_color = fields.Boolean(string='Hide Car Color')
    hide_odometer = fields.Boolean(string='Hide Odometer')
    hide_agency = fields.Boolean(string='Hide Agency')
    hide_salesperson = fields.Boolean(string='Hide Salesperson')
    hide_delivery_time = fields.Boolean(string='Hide Delivery Time')
    hide_sticker_removal = fields.Boolean(string='Hide Sticker Removal')

    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('wof_system_settings_company_unique', 'unique(company_id)', 'Only one car film settings record is allowed per company.'),
    ]

    @api.model
    def _default_company_id(self):
        company = self.env.company
        return company.parent_id.id or company.id

    @api.depends('company_id')
    def _compute_name(self):
        for rec in self:
            rec.name = _('Car Film Settings - %s') % (rec.company_id.display_name or '')

    @api.constrains('create_invoice_after_full_payment', 'auto_create_invoice_on_confirm')
    def _check_invoice_policy(self):
        for rec in self:
            if rec.create_invoice_after_full_payment and rec.auto_create_invoice_on_confirm:
                raise ValidationError(_('You cannot enable both invoice policies at the same time. Choose either after full payment or on confirmation.'))

    @api.model
    def get_company_settings(self, company=None):
        company = company or self.env.company
        company = company.parent_id or company
        settings = self.search([('company_id', '=', company.id)], limit=1)
        if not settings:
            settings = self.create({'company_id': company.id})
        return settings

    def action_open_current_company_settings(self):
        settings = self.get_company_settings()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Car Film Settings'),
            'res_model': 'wof.system.settings',
            'view_mode': 'form',
            'res_id': settings.id,
            'target': 'current',
        }
