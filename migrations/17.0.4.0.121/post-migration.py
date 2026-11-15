# -*- coding: utf-8 -*-
"""Technician tasks follow the employee card: refresh name and user of existing tasks."""


def migrate(cr, version):
    cr.execute("""
        UPDATE wof_technician_task t
           SET employee_user_id = e.user_id,
               employee_name = e.name
          FROM hr_employee e
         WHERE e.id = t.employee_id
    """)
