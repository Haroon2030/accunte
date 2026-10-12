FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_ENV=production

# لا أسرار هنا: كل الإعدادات الحساسة تُحقن وقت التشغيل من متغيرات البيئة (لوحة الاستضافة):
#   SECRET_KEY, DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, COOKIES_SECURE
#   + اختياري: ADMIN_USERNAME / ADMIN_PASSWORD (مدير أول مرة)، USE_R2 + R2_* لتخزين المرفقات
# الإقلاع يفشل عمدًا إن غاب SECRET_KEY أو DB_PASSWORD بدل العمل بقيم افتراضية.

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# الباك إند (Django) والواجهة الثابتة التي يقدّمها من نفس النطاق
COPY backend/ .
COPY frontend/ ./frontend/

RUN mkdir -p logs private_media && sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh

EXPOSE 8096

# الإقلاع قد ينتظر القاعدة دقائق (حدّ الاتصالات)، فمهلة البدء طويلة
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8096/healthz', timeout=4).status == 200 else 1)"

ENTRYPOINT ["./entrypoint.sh"]
