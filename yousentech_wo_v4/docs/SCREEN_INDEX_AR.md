# فهرس الشاشات

تقرير تدقيق الأساس: `FOUNDATION_AUDIT_AR.md`. تقرير اعتماد أمر التركيب:
`INSTALLATION_ORDER_AUDIT_AR.md`.
الحالات أدناه تعني اكتمال الكود والتوثيق؛ اختبار تشغيل Odoo الفعلي ما زال
مطلوبًا قبل الإنتاج.

| الشاشة | المفتاح | الحالة | التوثيق |
|---|---|---|---|
| التهيئة الأولى | `initial-setup` | MVP منفذ | `screens/initial_setup_AR.md` |
| مركز الإعدادات والجاهزية | `setup-center` | MVP منفذ | `screens/setup_center_AR.md` |
| أنشطة المركز | `service-types` | UX معتمد منفذ | `screens/service_types_AR.md` |
| محرر الخدمة/الفيلم ومكوّناته | `film-configuration` | UX معتمد منفذ | `screens/film_configuration_AR.md` |
| أسعار وعمولات المكوّنات | `advanced-pricing` | UX معتمد منفذ | `screens/advanced_pricing_AR.md` |
| أحجام السيارات | `car-sizes` | محسن | `screens/car_sizes_AR.md` |
| أجزاء السيارات | `car-parts` | محسن | `screens/car_parts_AR.md` |
| خيارات أجزاء السيارات | `car-part-options` | منفذ | `screens/car_part_options_AR.md` |
| الشركات المصنعة | `car-manufacturers` | منفذ | `screens/car_manufacturers_AR.md` |
| طرازات السيارات | `car-models` | محسن | `screens/car_models_AR.md` |
| سنوات الصنع | `car-years` | محسن | `screens/car_years_AR.md` |
| وكالات السيارات | `car-agencies` | محسن | `screens/car_agencies_AR.md` |
| المنتجات ومواد القياس | `products` | محسن | `screens/products_AR.md` |
| لوحة أوامر التركيب | `installation-orders-board` | MVP منفذ | `screens/installation_orders_board_AR.md` |
| أمر التركيب | `installation-order` | MVP منفذ | `screens/installation_order_AR.md` |
| خدمات وتسعير الأمر | `installation-order-services` | محدث لهيكل الخدمة | `screens/installation_order_services_AR.md` |
| استلام وفحص السيارة | `installation-order-intake` | MVP منفذ | `screens/installation_order_intake_AR.md` |
| تنفيذ الأمر والمواد | `installation-order-execution` | MVP منفذ | `screens/installation_order_execution_AR.md` |
| الجودة والتسليم | `installation-order-quality-delivery` | MVP منفذ | `screens/installation_order_quality_delivery_AR.md` |
| السجل الزمني للأمر | `installation-order-timeline` | MVP منفذ | `screens/installation_order_timeline_AR.md` |

أي شاشة تنتقل إلى «منفذة» يجب أن تحتوي وثيقتها على عقد التكامل مع Flutter
والصلاحيات والأخطاء والشاشات المرتبطة.
