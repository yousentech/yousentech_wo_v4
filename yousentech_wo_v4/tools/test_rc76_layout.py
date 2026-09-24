from pathlib import Path
css = Path('static/src/css/setup_wizard.css').read_text(encoding='utf-8')
checks = [
    'RC76 — True full-height setup sheet',
    '.modal-body:has(.wof_setup_form) .o_form_renderer',
    '.modal-body:has(.wof_setup_form) .o_form_sheet_bg',
    '.modal-body:has(.wof_setup_form) .wof_setup_sheet',
    'flex: 1 1 0 !important;',
]
missing = [x for x in checks if x not in css]
assert not missing, f'Missing RC76 layout rules: {missing}'
print('RC76_LAYOUT_OK')
