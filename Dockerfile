FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_ENV=production
ENV DB_NAME=accu
ENV DB_USER=accunt
ENV DB_PASSWORD=Haro@12345678
ENV DB_HOST=service-accuntdb-i90gt8
ENV DB_PORT=3306
ENV DEBUG=False
ENV SECRET_KEY=k8s-prod-x7m2p9qw4e6r1t3y5u8i0o2a4s6d8f0g
ENV ALLOWED_HOSTS=72.61.107.230,*
ENV CORS_ALLOWED_ORIGINS=http://72.61.107.230

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
