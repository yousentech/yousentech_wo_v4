from . import setup
from . import setup_wizard

def post_init_hook(env):
    env['wof.default.data.loader'].sudo().load_default_master_data()



def uninstall_hook(env):
    """Clean module-owned data on uninstall.

    The business expectation here is clear: when the module is removed,
    its setup/master/transient data should be removed too. We keep this
    cleanup conservative and use ORM unlink with savepoints so uninstall
    is not blocked by a single protected/dependent record.
    """
    model_names = [
        'wof.setup.temp.film.tint.degree.line',
        'wof.setup.temp.film.part.commission.line',
        'wof.setup.temp.film.part.price.line',
        'wof.setup.temp.film.part',
        'wof.setup.temp.film',
        'wof.setup.temp.film.board',
        'wof.setup.film.tint.degree.line',
        'wof.setup.film.part.commission.line',
        'wof.setup.film.part.price.line',
        'wof.setup.film.part.line',
        'wof.setup.film.wizard',
        'wof.setup.wizard.service.line',
        'wof.setup.wizard.tint.degree.line',
        'wof.setup.wizard.car.size.line',
        'wof.setup.wizard',
        'wof.system.settings',
        'wof.film.parts.commission.lines',
        'wof.film.parts.price.lines',
        'wof.film.parts.lines',
        'wof.film.category.lines',
        'wof.film.category',
        'wof.car.parts',
        'wof.tint.degree',
        'wof.service.type',
        'wof.car.size',
        'wof.car.types',
        'wof.car.manufactory.year',
        'wof.car.agency',
    ]

    for model_name in model_names:
        try:
            model = env[model_name].sudo()
            records = model.search([])
        except Exception:
            continue
        for record in records:
            try:
                with env.cr.savepoint():
                    record.unlink()
            except Exception:
                continue

    params = env['ir.config_parameter'].sudo().search([
        ('key', 'like', 'yousentech_wo_v4.%')
    ])
    params.unlink()
