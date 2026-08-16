# -*- coding: utf-8 -*-


ACTIVITY_KINDS = (
    'tint', 'ppf', 'nano', 'upholstery', 'floor_mats', 'others',
)


def _table_exists(cr, table):
    cr.execute('SELECT to_regclass(%s)', (table,))
    row = cr.fetchone()
    return bool(row and row[0])


def migrate(cr, version):
    """Preserve IDs while formalizing activity/service/grade semantics."""
    if not _table_exists(cr, 'wof_service_type'):
        return
    cr.execute(
        """
        UPDATE wof_service_type
           SET service_options = 'others'
         WHERE service_options IS NULL
            OR service_options = ''
            OR service_options NOT IN %s
        """,
        (ACTIVITY_KINDS,),
    )
    if not (
        _table_exists(cr, 'wof_film_category')
        and _table_exists(cr, 'wof_film_category_lines')
        and _table_exists(cr, 'wof_film_parts_lines')
    ):
        return
    # Grades from legacy non-tint services remain recoverable but are no longer
    # offered operationally. No configured activity/service/component is moved.
    cr.execute(
        """
        UPDATE wof_film_category_lines AS grade
           SET active = FALSE
          FROM wof_film_category AS service,
               wof_service_type AS activity
         WHERE grade.header_id = service.id
           AND service.service_type_id = activity.id
           AND activity.service_options != 'tint'
           AND grade.active IS DISTINCT FROM FALSE
        """
    )
    cr.execute(
        """
        UPDATE wof_film_parts_lines AS component
           SET film_category_line_id = NULL
          FROM wof_film_category AS service,
               wof_service_type AS activity
         WHERE component.header_id = service.id
           AND service.service_type_id = activity.id
           AND activity.service_options != 'tint'
           AND component.film_category_line_id IS NOT NULL
        """
    )
    cr.execute(
        """
        UPDATE wof_film_parts_lines AS component
           SET film_category_line_id = NULL
          FROM wof_film_category_lines AS grade
         WHERE component.film_category_line_id = grade.id
           AND grade.header_id != component.header_id
        """
    )
