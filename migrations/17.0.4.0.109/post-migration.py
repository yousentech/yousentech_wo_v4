# -*- coding: utf-8 -*-
"""Films keep a list of stock products: start it from the old default product
and the products of the film's tint grades."""


def migrate(cr, version):
    cr.execute("""
        INSERT INTO wof_film_stock_product_rel (film_id, product_id)
        SELECT id, default_product_id FROM wof_film_category WHERE default_product_id IS NOT NULL
        UNION
        SELECT header_id, product_id FROM wof_film_category_lines
         WHERE product_id IS NOT NULL AND header_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)
