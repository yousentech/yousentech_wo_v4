from . import setup
from . import setup_wizard

def post_init_hook(env):
    env['wof.default.data.loader'].sudo().load_default_master_data()
