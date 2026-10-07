from . import setup_wizard

from . import activity_dialog
from . import size_dialog
from . import tint_dialog

from . import activity_hub

from . import film_setup_wizard
from . import service_area_template_dialog
from . import service_area_template_tree_fix
from . import component_bulk_picker
from . import component_tint_policy_dialog

# Loaded here because it extends wof.company.profile, which is defined in setup_wizard.
from ..setup import discount_policy
