# دليل الألوان - Color Guide

## الألوان الأساسية (Primary - Blue)
| الاسم | الكود | الاستخدام |
|-------|-------|-----------|
| primary-50 | `#eff6ff` | خلفيات فاتحة |
| primary-100 | `#dbeafe` | hover خفيف |
| primary-200 | `#bfdbfe` | borders |
| primary-500 | `#3b82f6` | نصوص ثانوية |
| primary-600 | `#2563eb` | **الأزرار الرئيسية** |
| primary-700 | `#1d4ed8` | hover للأزرار |

## الألوان الرمادية (Slate)
| الاسم | الكود | الاستخدام |
|-------|-------|-----------|
| slate-50 | `#f8fafc` | خلفية الصفحة |
| slate-100 | `#f1f5f9` | خلفية الجدول header |
| slate-200 | `#e2e8f0` | borders, dividers |
| slate-300 | `#cbd5e1` | borders داكنة |
| slate-500 | `#64748b` | نصوص ثانوية |
| slate-600 | `#475569` | نصوص عادية |
| slate-700 | `#334155` | نصوص غامقة |
| slate-800 | `#1e293b` | عناوين |
| slate-900 | `#0f172a` | نصوص سوداء |

## ألوان الحالات

### أخضر (Success)
| الاسم | الكود | الاستخدام |
|-------|-------|-----------|
| green-50 | `#f0fdf4` | خلفية تنبيه نجاح |
| green-100 | `#dcfce7` | شارة نشط |
| green-600 | `#16a34a` | أيقونة نجاح |
| green-800 | `#166534` | نص شارة نشط |

### أحمر (Danger/Error)
| الاسم | الكود | الاستخدام |
|-------|-------|-----------|
| red-50 | `#fef2f2` | خلفية تنبيه خطأ |
| red-100 | `#fee2e2` | شارة معطل |
| red-600 | `#dc2626` | زر حذف، أيقونة خطأ |
| red-800 | `#991b1b` | نص شارة معطل |

### أصفر (Warning)
| الاسم | الكود | الاستخدام |
|-------|-------|-----------|
| yellow-50 | `#fefce8` | خلفية تنبيه تحذير |
| yellow-100 | `#fef9c3` | شارة معلق |
| yellow-500 | `#eab308` | زر تحذير |
| yellow-600 | `#ca8a04` | أيقونة تحذير |
| yellow-800 | `#854d0e` | نص شارة معلق |

### بنفسجي (Purple)
| الاسم | الكود | الاستخدام |
|-------|-------|-----------|
| purple-100 | `#f3e8ff` | شارة مميز |
| purple-600 | `#9333ea` | أيقونة مميز |
| purple-800 | `#6b21a8` | نص شارة مميز |

## أمثلة الاستخدام في Tailwind

### الأزرار
```html
<!-- زر أساسي -->
<button class="bg-primary-600 hover:bg-primary-700 text-white">

<!-- زر نجاح -->
<button class="bg-green-600 hover:bg-green-700 text-white">

<!-- زر خطر -->
<button class="bg-red-600 hover:bg-red-700 text-white">

<!-- زر ثانوي -->
<button class="border border-slate-200 hover:bg-slate-50">
```

### الشارات (Badges)
```html
<!-- نشط -->
<span class="bg-green-100 text-green-800">نشط</span>

<!-- معطل -->
<span class="bg-red-100 text-red-800">معطل</span>

<!-- معلق -->
<span class="bg-yellow-100 text-yellow-800">معلق</span>

<!-- جديد -->
<span class="bg-blue-100 text-blue-800">جديد</span>
```

### التنبيهات (Alerts)
```html
<!-- نجاح -->
<div class="bg-green-50 border-green-200 text-green-800">

<!-- خطأ -->
<div class="bg-red-50 border-red-200 text-red-800">

<!-- تحذير -->
<div class="bg-yellow-50 border-yellow-200 text-yellow-800">

<!-- معلومة -->
<div class="bg-blue-50 border-blue-200 text-blue-800">
```

### الكروت والجداول
```html
<!-- كارت -->
<div class="bg-white border-slate-200 shadow-sm rounded-xl">

<!-- header الجدول -->
<thead class="bg-slate-50 border-slate-200">

<!-- صف الجدول -->
<tr class="hover:bg-slate-50 border-slate-100">
```

## CSS Variables (اختياري)
```css
:root {
    --primary-50: #eff6ff;
    --primary-100: #dbeafe;
    --primary-500: #3b82f6;
    --primary-600: #2563eb;
    --primary-700: #1d4ed8;
    
    --success: #16a34a;
    --danger: #dc2626;
    --warning: #eab308;
    --info: #3b82f6;
}
```
