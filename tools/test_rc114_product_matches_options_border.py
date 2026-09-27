from pathlib import Path
p = Path(__file__).resolve().parents[1] / 'static/src/css/setup_wizard.css'
s = p.read_text(encoding='utf-8')
block = s[s.index('/* RC114'):]
assert '.wof_component_product_field > .o_field_widget' in block
assert '.o-autocomplete--input' in block
assert 'border:1px solid #cfdfe3!important' in block
assert 'border:0!important' in block
print('RC114 product single-border CSS OK')
