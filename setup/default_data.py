# -*- coding: utf-8 -*-
from odoo import api, models, _


class WofDefaultDataLoader(models.AbstractModel):
    _name = 'wof.default.data.loader'
    _description = 'WOF Default Master Data Loader'

    def _parent_company(self, company=None):
        company = company or self.env.company
        return company.parent_id or company

    def _service_defaults(self):
        return [
            {'sequence': 10, 'code': 'TINT', 'name': 'عزل حراري', 'service_options': 'tint', 'setup_enabled': False},
            {'sequence': 20, 'code': 'PPF', 'name': 'حماية PPF', 'service_options': False, 'setup_enabled': False},
            {'sequence': 30, 'code': 'NANO', 'name': 'نانو سيراميك', 'service_options': False, 'setup_enabled': False},
            {'sequence': 40, 'code': 'STRIP', 'name': 'إزالة الرواصق', 'service_options': False, 'setup_enabled': False},
        ]

    def _car_size_defaults(self):
        return [
            {'sequence': 10, 'code': 'S', 'name': 'صغير', 'selected': False},
            {'sequence': 20, 'code': 'M', 'name': 'متوسط', 'selected': False},
            {'sequence': 30, 'code': 'L', 'name': 'كبير', 'selected': False},
            {'sequence': 40, 'code': 'XL', 'name': 'كبير جداً', 'selected': False},
        ]

    def _tint_degree_defaults(self):
        return [
            {'sequence': 10, 'name': 'الدرجة 1', 'value': 'شفاف'},
            {'sequence': 20, 'name': 'الدرجة 2', 'value': '00'},
            {'sequence': 30, 'name': 'الدرجة 3', 'value': '01'},
            {'sequence': 40, 'name': 'الدرجة 4', 'value': '02'},
            {'sequence': 50, 'name': 'الدرجة 5', 'value': '03'},
            {'sequence': 60, 'name': 'الدرجة 6', 'value': '04'},
        ]

    def _car_part_defaults(self):
        return [
            {'priority_part': 10, 'code': 'FRONT', 'name': 'الزجاج الأمامي', 'part_type': 'car_part'},
            {'priority_part': 20, 'code': 'REAR', 'name': 'الزجاج الخلفي', 'part_type': 'car_part'},
            {'priority_part': 30, 'code': 'FD-R', 'name': 'الباب الأمامي يمين', 'part_type': 'car_part'},
            {'priority_part': 40, 'code': 'FD-L', 'name': 'الباب الأمامي يسار', 'part_type': 'car_part'},
            {'priority_part': 50, 'code': 'RD-R', 'name': 'الباب الخلفي يمين', 'part_type': 'car_part'},
            {'priority_part': 60, 'code': 'RD-L', 'name': 'الباب الخلفي يسار', 'part_type': 'car_part'},
            {'priority_part': 70, 'code': 'QTR-R', 'name': 'الربع الخلفي يمين', 'part_type': 'car_part'},
            {'priority_part': 80, 'code': 'QTR-L', 'name': 'الربع الخلفي يسار', 'part_type': 'car_part'},
            {'priority_part': 90, 'code': 'SUNROOF', 'name': 'فتحة السقف', 'part_type': 'car_part'},
            {'priority_part': 100, 'code': 'FULL', 'name': 'كامل السيارة', 'part_type': 'service_area'},
        ]

    def _default_service(self, company):
        Service = self.env['wof.service.type'].sudo()
        service = Service.search([('code', '=', 'TINT'), ('company_id', '=', company.id)], limit=1)
        if not service:
            service = Service.search([('name', '=', 'عزل حراري'), ('company_id', '=', company.id)], limit=1)
        if not service:
            vals = self._service_defaults()[0].copy()
            vals['company_id'] = company.id
            if 'sequence' not in Service._fields:
                vals.pop('sequence', None)
            if 'service_options' not in Service._fields:
                vals.pop('service_options', None)
            if 'setup_enabled' not in Service._fields:
                vals.pop('setup_enabled', None)
            if 'is_default_setup' in Service._fields:
                vals['is_default_setup'] = True
            service = Service.create(vals)
        return service

    @api.model
    def load_default_master_data(self, company=None):
        company = self._parent_company(company)
        Service = self.env['wof.service.type'].sudo()
        Size = self.env['wof.car.size'].sudo()
        Tint = self.env['wof.tint.degree'].sudo()
        Part = self.env['wof.car.parts'].sudo()

        for item in self._service_defaults():
            vals = item.copy()
            vals['company_id'] = company.id
            if 'sequence' not in Service._fields:
                vals.pop('sequence', None)
            if 'service_options' not in Service._fields:
                vals.pop('service_options', None)
            if 'setup_enabled' not in Service._fields:
                vals.pop('setup_enabled', None)
            if 'is_default_setup' in Service._fields:
                vals['is_default_setup'] = True
            domain = [('company_id', '=', company.id), ('code', '=', vals['code'])]
            rec = Service.search(domain, limit=1)
            if not rec:
                rec = Service.search([('company_id', '=', company.id), ('name', '=', vals['name'])], limit=1)
            if rec:
                update_vals = vals.copy()
                update_vals.pop('setup_enabled', None)
                rec.write(update_vals)
            else:
                Service.create(vals)

        for item in self._car_size_defaults():
            vals = {'name': item['name'], 'active': False}
            if 'sequence' in Size._fields:
                vals['sequence'] = item['sequence']
            if 'code' in Size._fields:
                vals['code'] = item['code']
            if 'is_default_setup' in Size._fields:
                vals['is_default_setup'] = True
            rec = Size.search([('name', '=', item['name'])], limit=1)
            if rec:
                update_vals = vals.copy()
                update_vals.pop('active', None)
                rec.write(update_vals)
            else:
                Size.create(vals)

        for item in self._tint_degree_defaults():
            vals = item.copy()
            vals.update({'company_id': company.id, 'active': False})
            if 'is_default_setup' in Tint._fields:
                vals['is_default_setup'] = True
            rec = Tint.search([('company_id', '=', company.id), ('value', '=', item['value'])], limit=1)
            if rec:
                update_vals = vals.copy()
                update_vals.pop('active', None)
                rec.write(update_vals)
            else:
                Tint.create(vals)

        tint_service = self._default_service(company)
        for item in self._car_part_defaults():
            vals = item.copy()
            vals.update({'company_id': company.id, 'service_type_id': tint_service.id, 'active': False})
            if 'is_default_setup' in Part._fields:
                vals['is_default_setup'] = True
            rec = Part.search([('name', '=', item['name'])], limit=1)
            if rec:
                update_vals = vals.copy()
                update_vals.pop('active', None)
                rec.write(update_vals)
            else:
                Part.create(vals)
        return True

    @api.model
    def reset_default_master_data(self, company=None):
        """Reset and rebuild default setup data safely.

        Business rule used by the settings button:
        - Remove module default records when they are not protected by real data.
        - Clear old setup wizard/transient data so the user starts again cleanly.
        - Recreate the default templates immediately.
        - The recreated templates are not selected in the wizard; the user chooses
          what to activate again from scratch.
        """
        company = self._parent_company(company)

        def safe_unlink(records):
            for rec in records:
                try:
                    with self.env.cr.savepoint():
                        rec.unlink()
                except Exception:
                    # If a default record is already referenced by real business data,
                    # keep it and let the loader update it instead of breaking links.
                    continue

        # Clean wizard/transient setup data first to avoid reopening old selections.
        wizard_models = [
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
        ]
        for model_name in wizard_models:
            if model_name in self.env:
                safe_unlink(self.env[model_name].sudo().search([]))

        Part = self.env['wof.car.parts'].sudo()
        Tint = self.env['wof.tint.degree'].sudo()
        Service = self.env['wof.service.type'].sudo()
        Size = self.env['wof.car.size'].sudo()

        if 'is_default_setup' in Part._fields:
            safe_unlink(Part.search([('company_id', '=', company.id), ('is_default_setup', '=', True)]))
        if 'is_default_setup' in Tint._fields:
            safe_unlink(Tint.search([('company_id', '=', company.id), ('is_default_setup', '=', True)]))
        if 'is_default_setup' in Service._fields:
            safe_unlink(Service.search([('company_id', '=', company.id), ('is_default_setup', '=', True)]))
        if 'is_default_setup' in Size._fields:
            safe_unlink(Size.search([('is_default_setup', '=', True)]))

        # Recreate/update the default records so the setup flow shows the base values again.
        self.load_default_master_data(company)

        # Reset means: bring templates back, but leave them unselected until the user chooses again.
        if 'setup_enabled' in Service._fields:
            Service.search([('company_id', '=', company.id), ('is_default_setup', '=', True)]).write({'setup_enabled': False})
        Size.search([('is_default_setup', '=', True)]).with_context(active_test=False).write({'active': False})
        Tint.search([('company_id', '=', company.id), ('is_default_setup', '=', True)]).with_context(active_test=False).write({'active': False})
        Part.search([('company_id', '=', company.id), ('is_default_setup', '=', True)]).with_context(active_test=False).write({'active': False})

        self.env['ir.config_parameter'].sudo().set_param('yousentech_wo_v4.setup_completed', False)
        return True
