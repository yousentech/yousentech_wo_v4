# -*- coding: utf-8 -*-
"""Move the employee flags «فني تركيب» / «مشرف تشغيل» and the technician
commission ratio into the installation team table (one row per branch)."""


def _has_column(cr, column):
    cr.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = 'hr_employee' AND column_name = %s",
        (column,),
    )
    return bool(cr.fetchone())


def migrate(cr, version):
    tech = _has_column(cr, 'is_wof_technician')
    sup = _has_column(cr, 'is_wof_supervisor')
    if not (tech or sup):
        return
    ratio = 'technician_commission_ratio' if _has_column(cr, 'technician_commission_ratio') else '100.0'
    tech_col = 'COALESCE(is_wof_technician, false)' if tech else 'false'
    sup_col = 'COALESCE(is_wof_supervisor, false)' if sup else 'false'
    cr.execute(f"""
        INSERT INTO wof_team_member (employee_id, name, user_id, company_id, is_technician, is_supervisor,
                                     commission_ratio, active, create_uid, write_uid, create_date, write_date)
        SELECT e.id, e.name, e.user_id, e.company_id, {tech_col}, {sup_col}, COALESCE({ratio}, 100.0), true,
               1, 1, now() at time zone 'UTC', now() at time zone 'UTC'
        FROM hr_employee e
        WHERE ({tech_col} OR {sup_col}) AND e.company_id IS NOT NULL
        ON CONFLICT (employee_id, company_id) DO NOTHING
    """)
    # Supervisors already used on orders join the team of the order's branch.
    cr.execute("""
        INSERT INTO wof_team_member (employee_id, name, user_id, company_id, is_technician, is_supervisor,
                                     commission_ratio, active, create_uid, write_uid, create_date, write_date)
        SELECT DISTINCT o.supervisor_id, e.name, e.user_id, o.company_id, false, true, 100.0, true,
               1, 1, now() at time zone 'UTC', now() at time zone 'UTC'
        FROM wof_installation_order o JOIN hr_employee e ON e.id = o.supervisor_id
        WHERE o.supervisor_id IS NOT NULL
        ON CONFLICT (employee_id, company_id) DO UPDATE SET is_supervisor = true
    """)
