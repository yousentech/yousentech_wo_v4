# -*- coding: utf-8 -*-

def migrate(cr, version):
    """Move RC46 user-level technician ratios to employees when that old column exists."""
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'res_users' AND column_name = 'technician_commission_ratio'
    """)
    if not cr.fetchone():
        return
    cr.execute("""
        UPDATE hr_employee e
           SET technician_commission_ratio = u.technician_commission_ratio
          FROM res_users u
         WHERE e.user_id = u.id
           AND u.technician_commission_ratio IS NOT NULL
    """)
