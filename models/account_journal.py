from odoo import models, fields, api
from odoo.exceptions import UserError

class journal(models.Model):
    _inherit = 'account.journal'

    collection_journal_flag = fields.Boolean(string='Collection journal')