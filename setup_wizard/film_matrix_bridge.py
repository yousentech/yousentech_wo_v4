# -*- coding: utf-8 -*-
"""Open the pricing & commission matrix from the film setup wizard and return."""

from odoo import _, models
from odoo.exceptions import ValidationError


class WofFilmSetupWizardMatrix(models.TransientModel):
    _inherit = 'wof.film.setup.wizard'

    def action_open_pricing_matrix(self):
        self.ensure_one()
        self._ensure_access()
        if not self.film_id:
            raise ValidationError(_('احفظ البيانات الأساسية والمكونات أولاً.'))
        return self.film_id.with_context(wof_matrix_wizard_id=self.id).action_open_pricing_matrix()

    def action_return_from_matrix(self, step=None):
        """Called by the matrix client action: refresh the wizard and reopen it."""
        self.ensure_one()
        self._ensure_access()
        if step in ('pricing', 'commission'):
            self.current_step = step
            self.pricing_tab = 'commission' if step == 'commission' else 'price'
        self._prepare_commercial_lines()
        return self._dialog_action()
