from pathlib import Path
css = (Path(__file__).parents[1] / 'static/src/css/setup_wizard.css').read_text(encoding='utf-8')
marker = 'RC80 — FIX review stage visibility'
assert marker in css, 'RC80 stage-5 visibility override missing'
block = css.split(marker, 1)[1]
assert '.wof_stage5_shell > .wof_stage5_review' in block
assert 'flex: 1 1 auto !important;' in block
assert 'height: auto !important;' in block
assert 'min-height: 1px !important;' in block
assert 'overflow: visible !important;' in block
assert '.wof_stage5_success' in block
print('RC80_STAGE5_VISIBILITY_OK')
