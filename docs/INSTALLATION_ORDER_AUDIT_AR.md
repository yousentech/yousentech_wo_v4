# تقرير اعتماد Installation Order MVP

التاريخ: 2026-07-30

الإصدار: `17.0.3.0.0`

النطاق: أمر التركيب فقط، من الاستقبال إلى التسليم.

## النتيجة

اكتمل كود Installation Order MVP وتوثيقه وعقد API المخطط، واجتاز أقصى
فحوصات ساكنة متاحة. لا توجد بيئة Odoo 17 أو PostgreSQL في مساحة العمل، لذلك
لم يُنفذ تثبيت/ترقية فعليان ولا اختبار متصفح، ولا يعد هذا التقرير بديلًا عنهما.

## ما تم تنفيذه

- `wof.installation.order`: العميل والسيارة والموعد والفريق والمجاميع والفحص
  والتنفيذ والجودة والتسليم والإلغاء والروابط المستقبلية.
- `wof.installation.order.line`: خدمة وفيلم ودرجة وجزء وتسعير الحجم والخصم
  والضريبة والعمولة المهيأة وتقدم التنفيذ.
- `wof.installation.material.line`: تسجيل المواد أثناء التنفيذ دون إنشاء حركة
  مخزون وهمية.
- `wof.installation.order.event`: سجل زمني append-only.
- انتقالات خادمية محمية، ورسائل عربية، ومنع الكتابة المباشرة للحالة والمصدر
  والمستخدم والتوقيتات.
- إنشاء idempotent على مستوى النموذج مع بصمة وتعارض صريح.
- UUID عام للعملاء والأوامر والخطوط والمواد والأحداث، وترحيل UUID للعملاء.
- Record rules للشركة، وقيد إضافي يجعل الفني يرى أوامره المسندة فقط.
- صلاحية مستقلة لاعتماد تجاوز السعر، مع سبب وسجل زمني وتدقيق.
- سياسة الخصم المهيأة مطبقة: خصم إجمالي أو خصم خدمات، قبل حساب الضريبة.
- واجهات كانبان وقائمة وبحث ونموذج RTL وHero واستجابة للجوال والتابلت.

## الشاشات ومساراتها

الكود البصري في `views/installation_order_views.xml` والتنسيق في
`static/src/css/installation_order.css`.

منطق الأعمال مفصول في:

- `models/installation_order.py`: البيانات والهوية والحسابات والإنشاء.
- `models/installation_order_workflow.py`: الصلاحيات والانتقالات والسجل.
- `models/installation_order_line.py`: الخدمات والتسعير والتنفيذ.
- `models/installation_material.py`: المواد المستخدمة.
- `models/installation_event.py`: أحداث timeline غير القابلة للتعديل.

| الشاشة/القسم | التوثيق |
|---|---|
| لوحة الأوامر | `screens/installation_orders_board_AR.md` |
| نموذج الأمر والـHero | `screens/installation_order_AR.md` |
| الخدمات والتسعير | `screens/installation_order_services_AR.md` |
| الاستلام والفحص | `screens/installation_order_intake_AR.md` |
| التنفيذ والمواد | `screens/installation_order_execution_AR.md` |
| الجودة والتسليم | `screens/installation_order_quality_delivery_AR.md` |
| السجل الزمني | `screens/installation_order_timeline_AR.md` |

## الفحوص المنفذة

- تجميع جميع ملفات Python: ناجح.
- تحليل جميع XML بـlxml وفحص XPath: ناجح.
- `tools/static_validation.py`: ناجح، ويغطي manifest والاعتماديات والملفات
  المحملة وexternal IDs وترتيب المراجع وحقول الواجهات والأزرار والنماذج
  والعلاقات وMonetary وACL وقواعد الشركات والتوثيق ومراجع OpenAPI.
- فحص صيغة Odoo 17: لا `attrs` أو `states` قديمة، والشروط modifiers مباشرة.
- فحص الأمان: لا `base.group_system` ولا `res.config.settings` ولا controllers.
- فحص `sudo`: موضعان فقط، لإدراج audit وtimeline append-only بعد تحقق العملية.
- فحص نصوص الملفات المعدلة: لا tabs أو مسافات زائدة.
- فحص توفر التشغيل: لا `odoo`, `odoo-bin`, `psql` ولا Python package باسم
  `odoo` في البيئة الحالية.

## ما لم يمكن اختباره

- `-i yousentech_wo_v4` و`-u yousentech_wo_v4` على قاعدة Odoo 17.
- إنشاء مستخدمين فعليين لكل دور واختبار record rules لشركتين.
- سلوك widgets والكانبان والـHero داخل متصفح Odoo الحقيقي.
- معاملات الضرائب المحلية ببيانات `account.tax` فعلية.
- سباق idempotency الحقيقي على PostgreSQL.

## القيود والمخاطر المتبقية

- أمر البيع والفاتورة والضمان روابط قراءة فقط؛ إنشاؤها وترحيلها في المراحل
  المالية والضمان، منعًا لازدواج البيانات.
- المواد سجل تشغيلي؛ `stock.move` الفعلي مؤجل لتكامل المخزون.
- موافقة العميل Boolean ومرجع اختياري، وليست OTP أو توقيعًا إلكترونيًا.
- المرفقات تعمل بواجهة Odoo الحالية؛ endpoint رفع آمن لم ينفذ.
- كل مسارات `/api/v1` في OpenAPI تحمل `x-implementation-status: planned`؛
  المصادقة وREST controllers لم تنفذ عمدًا.

## قرار الاعتماد

لا يوجد مانع ساكن معروف داخل نطاق Installation Order MVP. بوابة الإنتاج
المتبقية إلزامية: تثبيت/ترقية على Odoo 17 مع PostgreSQL، ثم اختبار الأدوار
والشركات والانتقالات والتسعير والـUX على الأجهزة المستهدفة. يتوقف العمل هنا
قبل بوابة العميل أو Flutter أو المراحل المالية المتقدمة.
