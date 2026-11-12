# -*- coding: utf-8 -*-
"""Ready car catalog: colours, makes and their models.

``wof.car.manufactory._wof_load_catalog`` runs on every install/upgrade. It adds
what is missing (matched by code or by name in Arabic or English) and never
changes or removes what users entered, so it is safe to run again.
"""

from odoo import api, fields, models

CAR_COLORS = [
    # code, Arabic, English, hex
    ('WHITE', 'أبيض', 'White', '#FFFFFF'), ('PEARL', 'أبيض لؤلؤي', 'Pearl White', '#F4F1EA'),
    ('BLACK', 'أسود', 'Black', '#111111'), ('SILVER', 'فضي', 'Silver', '#C0C4C8'),
    ('GREY', 'رمادي', 'Grey', '#808588'), ('DGREY', 'رمادي غامق', 'Dark Grey', '#4A4F52'),
    ('RED', 'أحمر', 'Red', '#C62828'), ('MAROON', 'عنابي', 'Maroon', '#6D1A24'),
    ('BLUE', 'أزرق', 'Blue', '#1E5BB8'), ('NAVY', 'كحلي', 'Navy', '#1B2A4A'),
    ('BROWN', 'بني', 'Brown', '#6B4A32'), ('BEIGE', 'بيج', 'Beige', '#D9C7A7'),
    ('GOLD', 'ذهبي', 'Gold', '#C9A34A'), ('CHAMPAGNE', 'شامبين', 'Champagne', '#E2CFA8'),
    ('GREEN', 'أخضر', 'Green', '#2E7D32'), ('ORANGE', 'برتقالي', 'Orange', '#E8711A'),
    ('YELLOW', 'أصفر', 'Yellow', '#F2C200'), ('PURPLE', 'بنفسجي', 'Purple', '#5E35B1'),
]

CAR_CATALOG = {
    # make code: (Arabic, English, [(model code, Arabic, English), ...])
    'TOYOTA': ('تويوتا', 'Toyota', [
        ('CAMRY', 'كامري', 'Camry'), ('COROLLA', 'كورولا', 'Corolla'), ('YARIS', 'يارس', 'Yaris'),
        ('LANDCRUISER', 'لاندكروزر', 'Land Cruiser'), ('PRADO', 'برادو', 'Prado'), ('HILUX', 'هايلكس', 'Hilux'),
        ('FORTUNER', 'فورتشنر', 'Fortuner'), ('RAV4', 'راف فور', 'RAV4'), ('AVALON', 'أفالون', 'Avalon'),
        ('RAIZE', 'رايز', 'Raize'), ('COROLLACROSS', 'كورولا كروس', 'Corolla Cross'), ('HIACE', 'هايس', 'Hiace'),
        ('SEQUOIA', 'سيكويا', 'Sequoia'), ('CHR', 'سي اتش ار', 'C-HR')]),
    'LEXUS': ('لكزس', 'Lexus', [
        ('LX', 'إل إكس', 'LX'), ('GX', 'جي إكس', 'GX'), ('RX', 'آر إكس', 'RX'), ('ES', 'إي إس', 'ES'),
        ('LS', 'إل إس', 'LS'), ('NX', 'إن إكس', 'NX'), ('IS', 'آي إس', 'IS')]),
    'HYUNDAI': ('هيونداي', 'Hyundai', [
        ('ELANTRA', 'إلنترا', 'Elantra'), ('SONATA', 'سوناتا', 'Sonata'), ('ACCENT', 'أكسنت', 'Accent'),
        ('TUCSON', 'توسان', 'Tucson'), ('SANTAFE', 'سنتافي', 'Santa Fe'), ('CRETA', 'كريتا', 'Creta'),
        ('AZERA', 'أزيرا', 'Azera'), ('PALISADE', 'باليسيد', 'Palisade'), ('STARIA', 'ستاريا', 'Staria'),
        ('KONA', 'كونا', 'Kona')]),
    'KIA': ('كيا', 'Kia', [
        ('K5', 'كي 5', 'K5'), ('CERATO', 'سيراتو', 'Cerato'), ('PEGAS', 'بيجاس', 'Pegas'),
        ('SPORTAGE', 'سبورتاج', 'Sportage'), ('SORENTO', 'سورينتو', 'Sorento'), ('CARNIVAL', 'كرنفال', 'Carnival'),
        ('SELTOS', 'سيلتوس', 'Seltos'), ('SONET', 'سونيت', 'Sonet'), ('TELLURIDE', 'تيلورايد', 'Telluride'),
        ('K8', 'كي 8', 'K8')]),
    'NISSAN': ('نيسان', 'Nissan', [
        ('PATROL', 'باترول', 'Patrol'), ('ALTIMA', 'ألتيما', 'Altima'), ('SUNNY', 'صني', 'Sunny'),
        ('MAXIMA', 'ماكسيما', 'Maxima'), ('XTRAIL', 'إكس تريل', 'X-Trail'), ('NAVARA', 'نافارا', 'Navara'),
        ('KICKS', 'كيكس', 'Kicks'), ('PATHFINDER', 'باثفايندر', 'Pathfinder'), ('URVAN', 'أورفان', 'Urvan')]),
    'HONDA': ('هوندا', 'Honda', [
        ('ACCORD', 'أكورد', 'Accord'), ('CIVIC', 'سيفيك', 'Civic'), ('CRV', 'سي آر في', 'CR-V'),
        ('PILOT', 'بايلوت', 'Pilot'), ('CITY', 'سيتي', 'City'), ('HRV', 'إتش آر في', 'HR-V')]),
    'CHEVROLET': ('شفروليه', 'Chevrolet', [
        ('TAHOE', 'تاهو', 'Tahoe'), ('SUBURBAN', 'سوبربان', 'Suburban'), ('SILVERADO', 'سلفرادو', 'Silverado'),
        ('MALIBU', 'ماليبو', 'Malibu'), ('CAPTIVA', 'كابتيفا', 'Captiva'), ('GROOVE', 'جروف', 'Groove'),
        ('TRAVERSE', 'ترافيرس', 'Traverse'), ('CAMARO', 'كامارو', 'Camaro')]),
    'GMC': ('جي إم سي', 'GMC', [
        ('YUKON', 'يوكن', 'Yukon'), ('SIERRA', 'سييرا', 'Sierra'), ('ACADIA', 'أكاديا', 'Acadia'),
        ('TERRAIN', 'تيرين', 'Terrain')]),
    'FORD': ('فورد', 'Ford', [
        ('EXPLORER', 'إكسبلورر', 'Explorer'), ('EXPEDITION', 'إكسبيديشن', 'Expedition'), ('F150', 'إف 150', 'F-150'),
        ('TAURUS', 'تورس', 'Taurus'), ('EDGE', 'إيدج', 'Edge'), ('TERRITORY', 'تيريتوري', 'Territory'),
        ('MUSTANG', 'موستنج', 'Mustang'), ('BRONCO', 'برونكو', 'Bronco'), ('RANGER', 'رينجر', 'Ranger')]),
    'MERCEDES': ('مرسيدس', 'Mercedes-Benz', [
        ('CCLASS', 'سي كلاس', 'C-Class'), ('ECLASS', 'إي كلاس', 'E-Class'), ('SCLASS', 'إس كلاس', 'S-Class'),
        ('GCLASS', 'جي كلاس', 'G-Class'), ('GLE', 'جي إل إي', 'GLE'), ('GLS', 'جي إل إس', 'GLS'),
        ('GLC', 'جي إل سي', 'GLC')]),
    'BMW': ('بي إم دبليو', 'BMW', [
        ('S3', 'الفئة الثالثة', '3 Series'), ('S5', 'الفئة الخامسة', '5 Series'), ('S7', 'الفئة السابعة', '7 Series'),
        ('X5', 'إكس 5', 'X5'), ('X6', 'إكس 6', 'X6'), ('X7', 'إكس 7', 'X7'), ('X3', 'إكس 3', 'X3')]),
    'MITSUBISHI': ('ميتسوبيشي', 'Mitsubishi', [
        ('PAJERO', 'باجيرو', 'Pajero'), ('ATTRAGE', 'أتراج', 'Attrage'), ('ASX', 'إيه إس إكس', 'ASX'),
        ('OUTLANDER', 'أوتلاندر', 'Outlander'), ('L200', 'إل 200', 'L200'), ('XPANDER', 'إكسباندر', 'Xpander')]),
    'MAZDA': ('مازدا', 'Mazda', [
        ('M3', 'مازدا 3', 'Mazda 3'), ('M6', 'مازدا 6', 'Mazda 6'), ('CX5', 'سي إكس 5', 'CX-5'),
        ('CX9', 'سي إكس 9', 'CX-9'), ('CX30', 'سي إكس 30', 'CX-30'), ('CX90', 'سي إكس 90', 'CX-90')]),
    'ISUZU': ('إيسوزو', 'Isuzu', [('DMAX', 'دي ماكس', 'D-Max'), ('MUX', 'إم يو إكس', 'MU-X')]),
    'SUZUKI': ('سوزوكي', 'Suzuki', [
        ('SWIFT', 'سويفت', 'Swift'), ('DZIRE', 'ديزاير', 'Dzire'), ('JIMNY', 'جيمني', 'Jimny'),
        ('CIAZ', 'سياز', 'Ciaz'), ('VITARA', 'فيتارا', 'Vitara'), ('ERTIGA', 'إرتيجا', 'Ertiga')]),
    'CHANGAN': ('شانجان', 'Changan', [
        ('CS35', 'سي إس 35', 'CS35'), ('CS75', 'سي إس 75', 'CS75'), ('CS85', 'سي إس 85', 'CS85'),
        ('ALSVIN', 'السفن', 'Alsvin'), ('EADO', 'إيدو', 'Eado'), ('UNIK', 'يوني كي', 'UNI-K'), ('UNIT', 'يوني تي', 'UNI-T')]),
    'GEELY': ('جيلي', 'Geely', [
        ('COOLRAY', 'كولراي', 'Coolray'), ('EMGRAND', 'إمجراند', 'Emgrand'), ('TUGELLA', 'توجيلا', 'Tugella'),
        ('MONJARO', 'مونجارو', 'Monjaro'), ('OKAVANGO', 'أوكافانجو', 'Okavango')]),
    'MG': ('إم جي', 'MG', [
        ('MG5', 'إم جي 5', 'MG5'), ('MG6', 'إم جي 6', 'MG6'), ('ZS', 'زد إس', 'ZS'), ('RX5', 'آر إكس 5', 'RX5'),
        ('HS', 'إتش إس', 'HS'), ('RX8', 'آر إكس 8', 'RX8'), ('GT', 'جي تي', 'GT')]),
    'HAVAL': ('هافال', 'Haval', [('H6', 'إتش 6', 'H6'), ('JOLION', 'جوليان', 'Jolion'), ('H9', 'إتش 9', 'H9'),
                                ('DARGO', 'دارجو', 'Dargo')]),
    'CHERY': ('شيري', 'Chery', [('TIGGO4', 'تيجو 4', 'Tiggo 4'), ('TIGGO7', 'تيجو 7', 'Tiggo 7'),
                                ('TIGGO8', 'تيجو 8', 'Tiggo 8'), ('ARRIZO6', 'أريزو 6', 'Arrizo 6')]),
    'JETOUR': ('جيتور', 'Jetour', [('X70', 'إكس 70', 'X70'), ('X90', 'إكس 90', 'X90'), ('DASHING', 'داشينج', 'Dashing'),
                                  ('T2', 'تي 2', 'T2')]),
    'JEEP': ('جيب', 'Jeep', [('GRANDCHEROKEE', 'جراند شيروكي', 'Grand Cherokee'), ('WRANGLER', 'رانجلر', 'Wrangler'),
                            ('COMPASS', 'كومباس', 'Compass')]),
    'DODGE': ('دودج', 'Dodge', [('CHARGER', 'تشارجر', 'Charger'), ('DURANGO', 'دورانجو', 'Durango'),
                               ('CHALLENGER', 'تشالنجر', 'Challenger'), ('RAM', 'رام', 'Ram')]),
    'LANDROVER': ('لاند روفر', 'Land Rover', [
        ('RANGEROVER', 'رينج روفر', 'Range Rover'), ('RRSPORT', 'رينج روفر سبورت', 'Range Rover Sport'),
        ('DEFENDER', 'ديفندر', 'Defender'), ('DISCOVERY', 'ديسكفري', 'Discovery'), ('EVOQUE', 'إيفوك', 'Evoque')]),
    'AUDI': ('أودي', 'Audi', [('A4', 'إيه 4', 'A4'), ('A6', 'إيه 6', 'A6'), ('A8', 'إيه 8', 'A8'),
                             ('Q5', 'كيو 5', 'Q5'), ('Q7', 'كيو 7', 'Q7'), ('Q8', 'كيو 8', 'Q8')]),
    'VOLKSWAGEN': ('فولكس واجن', 'Volkswagen', [('TERAMONT', 'تيرامونت', 'Teramont'), ('TOUAREG', 'طوارق', 'Touareg'),
                                               ('TIGUAN', 'تيجوان', 'Tiguan'), ('PASSAT', 'باسات', 'Passat'),
                                               ('GOLF', 'جولف', 'Golf')]),
    'PORSCHE': ('بورش', 'Porsche', [('CAYENNE', 'كايين', 'Cayenne'), ('MACAN', 'ماكان', 'Macan'),
                                   ('911', '911', '911'), ('PANAMERA', 'باناميرا', 'Panamera')]),
    'CADILLAC': ('كاديلاك', 'Cadillac', [('ESCALADE', 'إسكاليد', 'Escalade'), ('CT5', 'سي تي 5', 'CT5'),
                                        ('XT5', 'إكس تي 5', 'XT5')]),
    'INFINITI': ('إنفينيتي', 'Infiniti', [('QX80', 'كيو إكس 80', 'QX80'), ('QX60', 'كيو إكس 60', 'QX60'),
                                         ('Q50', 'كيو 50', 'Q50')]),
    'GENESIS': ('جينيسيس', 'Genesis', [('G80', 'جي 80', 'G80'), ('G90', 'جي 90', 'G90'), ('GV80', 'جي في 80', 'GV80'),
                                      ('GV70', 'جي في 70', 'GV70')]),
    'TESLA': ('تسلا', 'Tesla', [('MODEL3', 'موديل 3', 'Model 3'), ('MODELY', 'موديل واي', 'Model Y'),
                               ('MODELS', 'موديل إس', 'Model S'), ('MODELX', 'موديل إكس', 'Model X')]),
    'LUCID': ('لوسيد', 'Lucid', [('AIR', 'إير', 'Air'), ('GRAVITY', 'جرافيتي', 'Gravity')]),
}


class WofCarColor(models.Model):
    _name = 'wof.car.color'
    _description = 'لون السيارة'
    _order = 'sequence, name'

    code = fields.Char(string='الكود', index=True, copy=False)
    name = fields.Char(string='اللون', required=True, translate=True)
    color_hex = fields.Char(string='اللون (HEX)', help='لون العرض، مثل #FFFFFF.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [('car_color_code_unique', 'unique(code)', 'كود اللون مستخدم مسبقًا.')]


class WofCarManufactoryCatalog(models.Model):
    _inherit = 'wof.car.manufactory'

    @api.model
    def _wof_arabic_langs(self):
        return [code for code, _name in self.env['res.lang'].get_installed() if code.startswith('ar')]

    @api.model
    def _wof_find(self, model, code, names, extra=None):
        domain = list(extra or [])
        model = model.with_context(active_test=False)
        record = model.search(domain + [('code', '=', code)], limit=1)
        for lang in ['en_US'] + self._wof_arabic_langs():
            for name in names:
                if record:
                    return record
                record = model.with_context(lang=lang).search(domain + [('name', '=ilike', name)], limit=1)
        return record

    @api.model
    def _wof_create_named(self, model, values, arabic):
        """English name for every language, Arabic for the installed Arabic languages."""
        record = model.with_context(lang='en_US').create(values)
        for lang in self._wof_arabic_langs():
            record.with_context(lang=lang).write({'name': arabic})
        return record

    @api.model
    def _wof_load_catalog(self):
        Color = self.env['wof.car.color']
        for sequence, (code, ar, en, hex_value) in enumerate(CAR_COLORS, start=1):
            if not self._wof_find(Color, code, [ar, en]):
                self._wof_create_named(Color, {'code': code, 'name': en, 'color_hex': hex_value,
                                               'sequence': sequence * 10}, ar)
        Make = self.with_context(active_test=False)
        Model = self.env['wof.car.type']
        for make_code, (make_ar, make_en, car_models) in CAR_CATALOG.items():
            make = self._wof_find(Make, make_code, [make_ar, make_en])
            if not make:
                make = self._wof_create_named(Make, {'code': make_code, 'name': make_en}, make_ar)
            for model_code, model_ar, model_en in car_models:
                if not self._wof_find(Model, model_code, [model_ar, model_en], [('manufactory_id', '=', make.id)]):
                    self._wof_create_named(Model, {'code': model_code, 'name': model_en,
                                                   'manufactory_id': make.id}, model_ar)
        return True
