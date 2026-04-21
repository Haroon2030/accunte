# قالب التصميم - Design Template

## نظرة عامة
هذا القالب يستخدم:
- **Tailwind CSS 2.2.19** - للتنسيق
- **Alpine.js 3.13.3** - للتفاعلية
- **HTMX 1.9.10** - للتحديث الديناميكي
- **Lucide Icons 0.294.0** - للأيقونات
- **Cairo Font** - الخط العربي

## الملفات المطلوبة

### 1. Static Files (ضعها في `/static/`)
```
static/
├── css/
│   └── tailwind.min.css
└── js/
    ├── htmx.min.js
    ├── alpine.min.js
    └── lucide.min.js
```

### 2. Templates
```
templates/
├── base.html              # القالب الأساسي مع Sidebar
├── base_public.html       # القالب للصفحات العامة (login)
├── auth/
│   └── login.html         # صفحة تسجيل الدخول
└── pages/
    ├── list.html          # نموذج صفحة قائمة مع جدول
    ├── form.html          # نموذج صفحة إضافة/تعديل
    ├── dashboard.html     # لوحة التحكم مع إحصائيات
    └── components.html    # عناصر التصميم (أزرار، شارات، تنبيهات، مودال)
```

## الألوان الأساسية (Primary)
```css
--primary-50: #eff6ff;
--primary-100: #dbeafe;
--primary-500: #3b82f6;
--primary-600: #2563eb;
--primary-700: #1d4ed8;
```

## التثبيت

1. انسخ المجلدات إلى مشروعك
2. أضف المتغيرات في settings.py:
```python
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
```

3. أضف custom_tags templatetag (اختياري للـ navigation)

## روابط تحميل المكتبات
- Tailwind: https://cdn.tailwindcss.com/2.2.19
- Alpine.js: https://cdn.jsdelivr.net/npm/alpinejs@3.13.3/dist/cdn.min.js
- HTMX: https://unpkg.com/htmx.org@1.9.10
- Lucide: https://unpkg.com/lucide@0.294.0/dist/umd/lucide.min.js
