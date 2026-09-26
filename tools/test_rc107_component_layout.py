from pathlib import Path
p=Path('setup_wizard/film_setup_wizard_view.xml').read_text()
c=Path('static/src/css/setup_wizard.css').read_text()
assert 'wof_component_product_inline' in p
assert 'wof_component_product_field' in p
assert 'RC107' in c
assert 'grid-template-columns:minmax(0,1fr) 320px' in c
assert 'grid-template-columns:minmax(0,1fr) 300px' in c
print('RC107 layout checks passed')
