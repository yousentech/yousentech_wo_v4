def migrate(cr, version):
    # RC37 adds persistent policy fields on film component lines. Odoo's ORM
    # creates the columns during module upgrade; existing rows use safe defaults.
    return
