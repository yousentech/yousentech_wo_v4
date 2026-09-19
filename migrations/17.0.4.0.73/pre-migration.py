# -*- coding: utf-8 -*-


def migrate(cr, version):
    # RC73 changes only transient wizard state/CSS-safe behavior.
    # No persistent business data migration is required.
    return
