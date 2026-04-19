#!/usr/bin/env python3
"""
سكريبت لتحديث قالب Django بأسماء ملفات الـ Frontend الجديدة
يُشغَّل تلقائياً بعد كل بناء للـ frontend
"""
import os
import re
from pathlib import Path

# المسارات
BASE_DIR = Path(__file__).resolve().parent
DIST_INDEX = BASE_DIR / 'frontend' / 'dist' / 'index.html'
TEMPLATE_FILE = BASE_DIR / 'backend' / 'templates' / 'admin' / 'frontend.html'

def extract_assets_from_dist():
    """استخراج أسماء ملفات JS و CSS من index.html المبني"""
    if not DIST_INDEX.exists():
        print(f"❌ الملف غير موجود: {DIST_INDEX}")
        return None, None
    
    content = DIST_INDEX.read_text(encoding='utf-8')
    
    # استخراج اسم ملف JS
    js_match = re.search(r'src="/assets/(index-[^"]+\.js)"', content)
    js_file = js_match.group(1) if js_match else None
    
    # استخراج اسم ملف CSS
    css_match = re.search(r'href="/assets/(index-[^"]+\.css)"', content)
    css_file = css_match.group(1) if css_match else None
    
    return js_file, css_file

def update_template(js_file, css_file):
    """تحديث قالب Django بأسماء الملفات الجديدة"""
    if not TEMPLATE_FILE.exists():
        print(f"❌ القالب غير موجود: {TEMPLATE_FILE}")
        return False
    
    content = TEMPLATE_FILE.read_text(encoding='utf-8')
    
    # تحديث ملف JS
    if js_file:
        content = re.sub(
            r"{% static 'frontend/assets/index-[^']+\.js' %}",
            f"{{% static 'frontend/assets/{js_file}' %}}",
            content
        )
    
    # تحديث ملف CSS
    if css_file:
        content = re.sub(
            r"{% static 'frontend/assets/index-[^']+\.css' %}",
            f"{{% static 'frontend/assets/{css_file}' %}}",
            content
        )
    
    TEMPLATE_FILE.write_text(content, encoding='utf-8')
    return True

def main():
    print("🔄 تحديث قالب Django...")
    
    js_file, css_file = extract_assets_from_dist()
    
    if not js_file or not css_file:
        print("❌ فشل في استخراج أسماء الملفات")
        return 1
    
    print(f"📦 JS: {js_file}")
    print(f"🎨 CSS: {css_file}")
    
    if update_template(js_file, css_file):
        print("✅ تم تحديث القالب بنجاح!")
        return 0
    else:
        print("❌ فشل في تحديث القالب")
        return 1

if __name__ == '__main__':
    exit(main())
