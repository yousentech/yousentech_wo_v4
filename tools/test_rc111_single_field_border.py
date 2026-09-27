from pathlib import Path
css = Path(__file__).resolve().parents[1] / 'static/src/css/setup_wizard.css'
s = css.read_text(encoding='utf-8')
assert 'RC111 — single-border relational fields' in s
assert '.wof_component_existing_product_v4{' in s
assert 'border:0!important' in s[s.index('RC111 — single-border relational fields'):]
assert '.wof_component_create_form .o_field_many2many_tags .o_input' in s
assert 'box-shadow:none!important' in s[s.index('.wof_component_create_form .o_field_many2many_tags .o_input'):]
print('RC111 single-border relational fields test: OK')
