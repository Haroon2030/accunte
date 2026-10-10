FROM python:3.14-slim

# Force rebuild: 2026-04-19
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_ENV=production
ENV DEBUG=False

# لا أسرار هنا. كل الإعدادات الحساسة تُحقن وقت التشغيل من متغيرات البيئة (لوحة الاستضافة أو backend/.env):
#   SECRET_KEY, DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, ALLOWED_HOSTS
#   + اختياري: ADMIN_PASSWORD (لإنشاء مدير أول مرة), WHATSAPP_* (انظر backend/.env.example)
# الإقلاع يفشل عمدًا إن غاب SECRET_KEY أو DB_PASSWORD بدل العمل بقيم افتراضية.

WORKDIR /app

# Install system dependencies for mysqlclient
RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend project
COPY backend/ .

# Create logs directory
RUN mkdir -p logs

# Fix Windows line endings (CRLF -> LF) and set permissions
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh

EXPOSE 8096

ENTRYPOINT ["./entrypoint.sh"]
