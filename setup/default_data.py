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
                rec.write(vals)
            else:
                Service.create(vals)

        for item in self._car_size_defaults():
            vals = {'name': item['name'], 'active': True}
            if 'sequence' in Size._fields:
                vals['sequence'] = item['sequence']
            if 'code' in Size._fields:
                vals['code'] = item['code']
            if 'is_default_setup' in Size._fields:
                vals['is_default_setup'] = True
            rec = Size.search([('name', '=', item['name'])], limit=1)
            if rec:
                rec.write(vals)
            else:
                Size.create(vals)

        for item in self._tint_degree_defaults():
            vals = item.copy()
            vals.update({'company_id': company.id, 'active': True})
            if 'is_default_setup' in Tint._fields:
                vals['is_default_setup'] = True
            rec = Tint.search([('company_id', '=', company.id), ('value', '=', item['value'])], limit=1)
            if rec:
                rec.write(vals)
            else:
                Tint.create(vals)

        tint_service = self._default_service(company)
        for item in self._car_part_defaults():
            vals = item.copy()
            vals.update({'company_id': company.id, 'service_type_id': tint_service.id, 'active': True})
            if 'is_default_setup' in Part._fields:
                vals['is_default_setup'] = True
            rec = Part.search([('name', '=', item['name'])], limit=1)
            if rec:
                rec.write(vals)
            else:
                Part.create(vals)
        return True

    @api.model
    def reset_default_master_data(self, company=None):
        """Reset default setup safely.

        Important UX/business rule:
        - Reset from settings must NOT reload defaults automatically.
        - It deletes only records created by the default setup engine.
        - The system becomes unconfigured, then the user re-selects what to enable
          from the setup wizard, which reads Python templates as suggestions.
        """
        company = self._parent_company(company)

        def safe_unlink(records):
            for rec in records:
                try:
                    with self.env.cr.savepoint():
                        rec.unlink()
                except Exception:
                    # If a record is already used by real business data, keep it.
                    # This prevents breaking existing films/prices/orders.
                    continue

        safe_unlink(self.env['wof.car.parts'].sudo().search([
            ('company_id', '=', company.id), ('is_default_setup', '=', True),
        ]))
        safe_unlink(self.env['wof.tint.degree'].sudo().search([
            ('company_id', '=', company.id), ('is_default_setup', '=', True),
        ]))
        safe_unlink(self.env['wof.service.type'].sudo().search([
            ('company_id', '=', company.id), ('is_default_setup', '=', True),
        ]))
        if 'is_default_setup' in self.env['wof.car.size']._fields:
            safe_unlink(self.env['wof.car.size'].sudo().search([('is_default_setup', '=', True)]))

        self.env['ir.config_parameter'].sudo().set_param('yousentech_wo_v4.setup_completed', False)
        return True
