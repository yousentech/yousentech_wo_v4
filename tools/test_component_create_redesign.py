from pathlib import Path
import re
ROOT = Path(__file__).resolve().parents[1]
xml = (ROOT/'setup_wizard/film_setup_wizard_view.xml').read_text(encoding='utf-8')
css = (ROOT/'static/src/css/setup_wizard.css').read_text(encoding='utf-8')
start = xml.index('id="view_wof_film_setup_component_create_dialog_form"')
end = xml.index('id="view_wof_film_setup_value_dialog_form"')
view = xml[start:end]
required = ['name="name"','name="code"','name="auto_create_product"','name="product_id"',
            'name="priority_part"','name="service_area_part_ids"','name="part_options_required"',
            'name="part_options_ids"','name="notes"','name="warning_msg"',
            'name="action_back_to_selection"','name="action_create_and_add"']
missing = [x for x in required if x not in view]
assert not missing, f'missing fields/actions: {missing}'
assert '<details class="wof_component_create_advanced' not in view, 'advanced fields must be visible, not hidden in details'
assert 'wof_component_create_options_card' in view, 'visible options card missing'
assert 'RC102' in css and '#27858a' in css, 'approved teal visual override missing'
print('component create redesign contract: OK')
assert 'wof_component_preview_compact' not in view, 'component preview summary must be removed'
assert 'wof_component_product_mode_v6' in view, 'unified service product card layout missing'
assert view.index('name="auto_create_product"') < view.index('name="product_id"'), 'auto-create toggle should precede existing product field'
# RC110: required-options flag is compact and lives beside the options label, not in a separate card.
assert 'wof_component_options_label_row' in view, 'compact options label row missing'
assert '<strong>إلزام الاختيار</strong>' in view, 'compact required-options label missing'
assert 'إلزام المستخدم بالخيارات الإضافية عند التشغيل.' not in view, 'old long required-options help text must be removed'
assert '<div class="wof_component_required_option">' not in view, 'old standalone required-options card must be removed'
