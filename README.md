# بوابة مطابقة الموردين

واجهة (React بلا بناء) تتصل بـ API من Django، وتُقدَّم كلها من نفس النطاق بجلسات آمنة.

```
frontend/   الواجهة: index.html (الموظفون) و supplier.html (بوابة الموردين) + js/ و css/
backend/    Django: apps/accounts (الدخول والمستخدمون) و apps/matching (الطلبات والشكاوى والمراسلات والمرفقات)
Dockerfile  يبني الصورة (يضم backend و frontend) — بنفس مسار النشر الحالي في Dokploy
```

## المسارات
| المسار | الوظيفة |
|---|---|
| `/` | واجهة الموظفين: المطابق، المدير المالي، مدير النظام |
| `/portal/` (و`/supplier/`) | بوابة الموردين |
| `/api/...` | JSON: `auth/` و`users/` و`bootstrap/` و`requests/` و`complaints/` و`attachments/` و`seen/` |
| `/admin/` | لوحة Django لمدير النظام |
| `/healthz` | فحص الصحة |

الأدوار: مورد، مطابق، مدير مالي، مدير نظام. الصلاحيات تُفرض في الخادم عند كل طلب (الواجهة لا تُؤتمن).

## تشغيل محلي
```bash
cd backend
python -m venv venv && venv/Scripts/pip install -r requirements.txt   # أو venv/bin على لينكس
venv/Scripts/python manage.py migrate
venv/Scripts/python manage.py seed_demo       # حسابات تجريبية (DEBUG فقط)
venv/Scripts/python manage.py runserver
venv/Scripts/python manage.py test apps
```

## الإنتاج (Dokploy)
متغيرات البيئة المطلوبة: `SECRET_KEY`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`,
`ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `COOKIES_SECURE=true`.
اختيارية: `ADMIN_USERNAME` / `ADMIN_PASSWORD` (إنشاء مدير النظام أول مرة)، و`USE_R2=True` مع `R2_*` لتخزين المرفقات.
الإقلاع: ينتظر القاعدة، ثم `migrate`، ثم `bootstrap_admin`، ثم `collectstatic`، ثم gunicorn.

### تنظيف جداول المشروع القديم (يدوي ومتعمَّد)
```bash
python manage.py drop_legacy_tables          # يعرض ما سيُحذف فقط (dry-run)
python manage.py drop_legacy_tables --yes    # يحذف فعلاً. لا رجعة فيه: خذ نسخة احتياطية أولاً
```
النسخة الكاملة من الكود القديم محفوظة في وسم git باسم `legacy-v1`.
