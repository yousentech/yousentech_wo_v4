from pathlib import Path

css = (Path(__file__).resolve().parents[1] / 'static/src/css/component_tree_compact.css').read_text(encoding='utf-8')

assert 'RC116' in css, 'RC116 compact-row rules are missing'
assert 'min-height: 34px !important;' in css, 'top-level component/service-area rows must be compact'
assert 'padding: 3px 8px !important;' in css, 'top-level component/service-area vertical padding must be reduced'
assert 'margin: 0 0 2px !important;' in css, 'kanban row spacing must be reduced without removing separation'
assert 'height: 24px !important;' in css, 'row controls must remain compact'
print('RC116 compact component/service-area row checks passed')
