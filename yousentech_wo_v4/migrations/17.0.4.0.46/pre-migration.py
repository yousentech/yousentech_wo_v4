# -*- coding: utf-8 -*-
"""RC46 schema migration.

New commission configuration columns are additive and are created by Odoo's ORM
on module upgrade.  Existing commission rows remain fixed-amount by default,
which preserves legacy behaviour.
"""


def migrate(cr, version):
    # No destructive SQL is required. Defaults are applied by the ORM.
    return
