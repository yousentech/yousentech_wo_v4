# -*- coding: utf-8 -*-


def migrate(cr, version):
    # No schema/data rewrite is required for RC64 commission-entry tracking.
    # The hook intentionally wires the release into Odoo's upgrade chain.
    return
