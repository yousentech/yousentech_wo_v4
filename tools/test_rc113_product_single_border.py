from pathlib import Path
s = Path(__file__).resolve().parents[1].joinpath('static/src/css/setup_wizard.css').read_text()
assert 'RC113 — product selector: exactly one visible border.' in s
block = s.split('RC113 — product selector: exactly one visible border.', 1)[1]
assert '.wof_component_create_form .wof_component_product_field .o_field_many2one{' in block
assert 'border:0!important;' in block
assert '.wof_component_create_form .wof_component_product_field .o_field_many2one .o_input{' in block
assert 'border:1px solid #cfdfe3!important;' in block
print('RC113 product selector single-border CSS OK')
