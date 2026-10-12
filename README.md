# بوابة مطابقة الموردين

افتح `index.html` في المتصفح (يحتاج إنترنت لتحميل React ومكتبات قراءة الملفات).

## الدخول
الحسابات تُنشأ بأمر `create_portal_user` (انظر قسم الباك إند)، وكلمات المرور لا تُكتب في الملفات.


## الشاشات (الأدوار)
1. المورد: خدمات المطابقة، طلبات المطابقة، شكوى المدير المالي، التتبع والمحادثة.
2. المطابق: معالجة الطلبات والتتبع والمحادثة.
3. المدير المالي: لوحة المتابعة والشكاوى.
5. إدارة المستخدمين (المدير المالي ومدير النظام): إضافة وتعديل وإيقاف وإعادة تعيين كلمة المرور وجدول الصلاحيات.
4. مطابقة الكشوف (داخلية للمطابقين والمدير المالي، لا تظهر للمورد): تقرأ Excel / CSV / Word / PDF / صورة وتخرج الفروقات وبيان التسوية.

## ملاحظات
- المشروع ملف واحد (React 18 UMD) والبيانات الحالية تجريبية.
- قراءة الصور وPDF الممسوح (OCR) غير مختبرة على ملفات حقيقية.
- الخطوة التالية للإنتاج: Django + PostgreSQL + Celery/Redis + Channels.

## الباك إند (Django)
المجلد `backend/`: Django + DRF، قاعدة MySQL، والملفات (PDF / Excel / CSV / صور، حتى 15 ميجابايت) تُحفظ في Cloudflare R2 تحت المسار `accounting/`.
الواجهة تُقدَّم من نفس الخادم، فلا حاجة لإعداد CORS.

التشغيل على السيرفر (الإعدادات من `backend/.env`، وهو غير مرفوع للنسخ):

```bash
cd backend
pip install -r requirements.txt
python manage.py migrate
PORTAL_PASSWORD='...' python manage.py create_portal_user --username 1 --role admin --name "مدير النظام" --force-change
PORTAL_PASSWORD='...' python manage.py create_portal_user --username 2 --role manager --name "المدير المالي" --force-change
PORTAL_PASSWORD='...' python manage.py create_portal_user --username 3 --role matcher --name "المطابق" --force-change
PORTAL_PASSWORD='...' python manage.py create_portal_user --username 4 --role supplier --name "مسؤول المورد" --org "اسم المورد" --code S-1001 --tax-no 300000000000003 --force-change
python manage.py collectstatic --noinput
gunicorn config.wsgi --bind 0.0.0.0:8000
```

للتجربة محلياً بدون MySQL و R2:
`DJANGO_ENV=development DB_ENGINE=django.db.backends.sqlite3 DB_NAME=local.sqlite3 USE_R2=False python manage.py runserver`
واختبارات الباك إند: `python manage.py test portal`.

- الموظفون يدخلون من `/` والموردون من `/supplier.html`.
- الشكاوى للمورد والمدير المالي ومدير النظام فقط، وإدارة المستخدمين لمدير النظام فقط.
- كل تنزيل ملف يمر عبر الخادم ويتحقق من الصلاحية (المورد لا يرى إلا ملفاته).
