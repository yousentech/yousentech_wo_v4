from odoo import models, fields, api

class OilExpense(models.Model):
    _name = 'oil.expense'
    _description = 'Oil Workshop Expense'

    name = fields.Char(string='Description', required=True)
    shift_id = fields.Many2one('oil.shift', string='Shift',ondelete="cascade")
    amount = fields.Float(string='Amount', required=True, digits='Product Price')
    date = fields.Datetime(string='Date', default=fields.Datetime.now)
    user_id = fields.Many2one('res.users', string='Responsible', default=lambda self: self.env.user)
    note = fields.Text(string='Notes')

    @api.model
    def create(self, vals):
        rec = super().create(vals)
        if rec.shift_id:
            rec.shift_id._compute_totals()
        return rec
