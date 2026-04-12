from odoo import models, fields, api, _
from odoo.exceptions import UserError

class OilShift(models.Model):
    _name = 'oil.shift'
    _description = 'Oil Workshop Shift'
    _order = 'start_time desc'

    name = fields.Char(string='Shift Reference', required=True, copy=False, readonly=True, default='New')
    user_id = fields.Many2one('res.users', string='Employee', default=lambda self: self.env.user, required=True)
    company_id = fields.Many2one('res.company', string='Branch', default=lambda self: self.env.company)
    collector_journal_id = fields.Many2one('account.journal', string='Collector',domain=[('collection_journal_flag','=',True)])
    start_time = fields.Datetime(string='Start Time', default=fields.Datetime.now)
    end_time = fields.Datetime(string='End Time')
    cash_start = fields.Float(string='Cash Start', digits='Product Price')
    cash_end = fields.Float(string='Cash End', digits='Product Price')
    sale_total = fields.Float(string='Sales Total', digits='Product Price', compute='_compute_totals', store=True)
    sale_cash_total = fields.Float(string='Cash Sales Total', digits='Product Price', compute='_compute_totals', store=True)
    sale_card_total = fields.Float(string='Card Sales Total', digits='Product Price', compute='_compute_totals', store=True)
    expense_total = fields.Float(string='Expenses Total', digits='Product Price', compute='_compute_totals', store=True)
    expected_cash = fields.Float(string='Expected Cash', digits='Product Price', compute='_compute_expected', store=True)
    difference = fields.Float(string='Remaining Cash', digits='Product Price', compute='_compute_difference', store=True)
    sales_difference = fields.Float(string='Sales Not Paid', digits='Product Price', compute='_compute_difference', store=True)
    orders_num = fields.Float(string='Orders Num', digits='Product Price', compute='_compute_difference', store=True)
    orders_invoiced_num = fields.Float(string='Orders Invoiced Num', digits='Product Price', compute='_compute_difference', store=True)
    order_difference = fields.Float(string='Orders Difference', digits='Product Price', compute='_compute_difference', store=True)

    note = fields.Text(string='Notes')
    state = fields.Selection([('open','Open'),('closed','Closed')], default='open', string='Status', tracking=True)

    sale_ids = fields.One2many('oil.work.order', 'shift_id', string='Work Orders')
    expense_ids = fields.One2many('oil.expense', 'shift_id', string='Expenses')

    @api.model
    def create(self, vals):
 
        open_shifts = self.search([
            ('company_id', '=', self.env.company.id),
            ('state', '=', 'open')
        ])
        if open_shifts:
            raise UserError(_(
                'You already have an open shift (%s). Close it before opening a new one.'
            ) % (open_shifts[0].name))

 
      
  
        user = vals.get('user_id') or self.env.user.id

        return super().create(vals)


    # def action_open_shift(self):
    #     for rec in self:
    #         existing = self.search([('user_id','=',rec.user_id.id),('state','=','open'),('id','!=',rec.id)])
        #         if existing:
    #             raise UserError(_('Cannot open this shift because another open shift exists (%s).') % existing[0].name)
    #         rec.state = 'open'
    #         rec.start_time = fields.Datetime.now()

    def action_close_shift(self):
        for rec in self:
            if rec.state != 'open':
                raise UserError(_('Shift is not open.'))
            # if not rec.collector_journal_id:
            #      raise UserError(_('PLease select collector.'))
            rec._compute_totals()
            rec._compute_expected()
            rec._compute_difference()
            rec.end_time = fields.Datetime.now()
            if rec.order_difference:
                if rec.orders_num > rec.orders_invoiced_num:
                    raise UserError(_('Warning: No. of order more than order invoiced please confirm it or delete it. (diff order: %s)' % rec.order_difference))
            if rec.sales_difference:
                raise UserError(_('Warning: there are Unpaid Invoices. (Total of unpaid invoices: %s)' % rec.sales_difference))
          

            rec.state = 'closed'
            
            if rec.name == 'New':
                seq = self.env['ir.sequence'].with_company(self.company_id.id).next_by_code('oil.shift')
                self.write({'name': seq or 'New' }) 


        return True
    def cancel_close_shift(self):
        for rec in self:
            rec.write({'state': 'open'})
    
    def refresh_result(self):
        for rec in self:
            rec._compute_totals()
            rec._compute_expected()
            rec._compute_difference()
    def unlink(self):
        for rec in self:
            if len(rec.sale_ids):
                   raise UserError(_('you can not deleted because the Shift data is related with work order.'))
            if rec.state == 'closed':
                raise UserError(_('you can not deleted because the Shift state is closed.'))

        return super().unlink()


    @api.depends('sale_ids.amount_total','expense_ids.amount')
    def _compute_totals(self):
        for rec in self:
            cash_sum = 0.0
            card_sum = 0.0
            sale_total = 0.0
            
            for s in rec.sale_ids:
                # assume oil.work.order has fields: amount_total and payment_type
                sale_total += s.amount_total
            for wo_id in rec.sale_ids:
                cash_sum += wo_id.get_cash_payment_amount(wo_id.account_move_id) or 0.0
            
                card_sum += wo_id.get_bank_payment_amount(wo_id.account_move_id) or 0.0

            rec.sale_total = sale_total
            rec.sale_cash_total = cash_sum
            rec.sale_card_total = card_sum
            rec.expense_total = sum(rec.expense_ids.mapped('amount')) or 0.0

    @api.depends('cash_start','sale_cash_total','expense_total','sale_total','cash_end')
    def _compute_expected(self):
        for rec in self:
            rec.expected_cash = (rec.cash_start or 0.0) +  (rec.sale_cash_total or 0.0) - (rec.expense_total or 0.0)

    @api.depends('expected_cash','cash_end')
    def _compute_difference(self):
        for rec in self:
            rec.difference = (rec.cash_end or 0.0) - (rec.expected_cash or 0.0)
            rec.sales_difference = ((rec.sale_total or 0.0) ) - ((rec.sale_cash_total or 0.0) + (rec.sale_card_total or 0.0) )
            rec.orders_invoiced_num = len(rec.sale_ids.account_move_id.ids)
            rec.orders_num = len(rec.sale_ids.ids)
            rec.order_difference = rec.orders_num - rec.orders_invoiced_num 

    def action_print_thermal(self):
        """طباعة تقرير الشفت بالطابعة الحرارية"""
        self.ensure_one()
        return self.env.ref('yousentech_oil_workshop_shift.action_report_oil_shift_thermal').report_action(self)

    def action_print_normal(self):
        """طباعة تقرير الشفت الرسمي للتوقيع"""
        self.ensure_one()
        return self.env.ref('yousentech_oil_workshop_shift.action_report_oil_shift_formal').report_action(self)
