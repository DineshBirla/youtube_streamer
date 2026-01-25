# Production Configuration Reference

## Quick Start Environment Variables

Copy this to your `.env` file and update with your values:

```bash
# ============ SECURITY ============
SECRET_KEY=your-super-secret-key-here-change-this
DEBUG=False
ENVIRONMENT=production
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com,api.yourdomain.com

# ============ DATABASE ============
DB_HOST=your-database-host.rds.amazonaws.com
DB_PORT=5432
DB_NAME=youtubestreamer_prod
DB_USER=postgres
DB_PASSWORD=your-secure-password

# ============ REDIS CACHE ============
REDIS_URL=redis://:password@your-redis-host:6379/1
CELERY_BROKER_URL=redis://:password@your-redis-host:6379/0
CELERY_RESULT_BACKEND=redis://:password@your-redis-host:6379/0

# ============ AWS S3 STORAGE ============
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_STORAGE_BUCKET_NAME=your-bucket-name
AWS_S3_REGION_NAME=us-east-1

# ============ YOUTUBE API ============
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=https://yourdomain.com/oauth/callback/

# ============ PAYMENTS (RAZORPAY) ============
RAZORPAY_KEY_ID=your-razorpay-key-id
RAZORPAY_KEY_SECRET=your-razorpay-secret

# ============ FFMPEG PATH ============
FFMPEG_PATH=/usr/bin/ffmpeg
```

---

## Optimized Configuration Files

### 1. Docker Compose (Production)

```yaml
version: '3.8'

services:
  web:
    image: youtubestreamer:latest
    container_name: youtubestreamer_web
    environment:
      DEBUG: "False"
      ENVIRONMENT: production
      DB_HOST: db
      REDIS_URL: redis://redis:6379/1
    ports:
      - "8000:8000"
    depends_on:
      - db
      - redis
    volumes:
      - ./apps:/app/apps
      - ./logs:/var/log/youtube_streamer
      - /var/tmp/streams:/var/tmp/streams
    restart: always
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  db:
    image: postgres:15-alpine
    container_name: youtubestreamer_db
    environment:
      POSTGRES_DB: youtubestreamer_prod
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: secure_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: always
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: youtubestreamer_redis
    command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    restart: always
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  celery:
    image: youtubestreamer:latest
    container_name: youtubestreamer_celery
    command: celery -A config worker -l info -c 2
    environment:
      DEBUG: "False"
      ENVIRONMENT: production
      DB_HOST: db
      REDIS_URL: redis://redis:6379/1
    depends_on:
      - db
      - redis
    volumes:
      - ./apps:/app/apps
      - ./logs:/var/log/youtube_streamer
      - /var/tmp/streams:/var/tmp/streams
    restart: always

volumes:
  postgres_data:
  redis_data:
```

### 2. Nginx Configuration

```nginx
upstream django {
    server web:8000;
}

server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    ssl_certificate /etc/ssl/certs/cert.pem;
    ssl_certificate_key /etc/ssl/private/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Gzip compression (NOTE: Django GZipMiddleware handles this)
    # Keeping both for redundancy
    gzip on;
    gzip_types text/plain text/css application/json;
    gzip_min_length 1000;

    client_max_body_size 100M;

    # Cache static files for 1 year
    location /static/ {
        alias /app/staticfiles/;
        expires 365d;
        add_header Cache-Control "public, immutable";
    }

    # Cache media files for 30 days
    location /media/ {
        alias /app/media/;
        expires 30d;
        add_header Cache-Control "public";
    }

    # Django application
    location / {
        proxy_pass http://django;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 30s;
    }
}
```

### 3. Systemd Service File

```ini
[Unit]
Description=YouTube Streamer Django Application
After=network.target postgresql.service redis.service

[Service]
Type=notify
User=www-data
WorkingDirectory=/home/www-data/youtubestreamer
Environment="PATH=/home/www-data/youtubestreamer/venv/bin"
Environment="DJANGO_SETTINGS_MODULE=config.settings"
Environment="DEBUG=False"
Environment="ENVIRONMENT=production"

# Start service
ExecStart=/home/www-data/youtubestreamer/venv/bin/gunicorn \
    --workers=4 \
    --worker-class=sync \
    --bind=0.0.0.0:8000 \
    --timeout=30 \
    --access-logfile=/var/log/youtubestreamer/access.log \
    --error-logfile=/var/log/youtubestreamer/error.log \
    config.wsgi:application

# Restart policy
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 4. Gunicorn Configuration

```python
# config/gunicorn_config.py
import multiprocessing

# Server socket
bind = "0.0.0.0:8000"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# Server mechanics
daemon = False
pidfile = "/var/run/gunicorn.pid"
umask = 0
user = None
group = None

# Logging
accesslog = "/var/log/youtubestreamer/access.log"
errorlog = "/var/log/youtubestreamer/error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "youtube_streamer"
```

### 5. PostgreSQL Configuration (Production)

```ini
# postgresql.conf - Key optimizations

# Connection settings
max_connections = 200
reserved_connections = 10

# Memory settings
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
work_mem = 8MB

# Query optimization
random_page_cost = 1.1
effective_io_concurrency = 200

# Logging
log_min_duration_statement = 1000  # Log queries > 1 second
log_connections = on
log_disconnections = on
log_duration = off
log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h '
```

### 6. Redis Configuration (Production)

```ini
# redis.conf - Key settings

port 6379
bind 127.0.0.1
timeout 0

# Memory management
maxmemory 512mb
maxmemory-policy allkeys-lru

# Persistence
save 900 1
save 300 10
save 60 10000

# Append only file
appendonly yes
appendfsync everysec

# Logging
loglevel notice
```

---

## Performance Tuning Recommendations

### For AWS RDS PostgreSQL

```sql
-- Execute these as superuser

-- Create indexes for common queries
CREATE INDEX idx_stream_user_created ON streaming_stream(user_id, created_at DESC);
CREATE INDEX idx_stream_status ON streaming_stream(status);
CREATE INDEX idx_mediafile_user ON streaming_mediafile(user_id);
CREATE INDEX idx_streamlog_stream ON streaming_streamlog(stream_id);

-- Analyze table statistics
ANALYZE streaming_stream;
ANALYZE streaming_mediafile;
ANALYZE streaming_streamlog;

-- Set auto-explain for slow queries
CREATE EXTENSION IF NOT EXISTS auto_explain;
SET auto_explain.log_min_duration = 1000;
SET auto_explain.log_analyze = true;
```

### For Redis Optimization

```bash
# Monitor Redis memory and performance
redis-cli INFO stats
redis-cli INFO memory

# Check connected clients
redis-cli CLIENT LIST

# Monitor slow commands
redis-cli --latency

# Clear expired keys
redis-cli FLUSHDB ASYNC
```

---

## Health Check Endpoint

Add this to `config/urls.py`:

```python
from django.http import JsonResponse
from django.views.decorators.cache import cache_page

@cache_page(60)  # Cache for 60 seconds
def health_check(request):
    """Simple health check endpoint"""
    from django.db import connection
    from django.core.cache import cache
    
    health = {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
    }
    
    # Check database
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        health['database'] = 'ok'
    except Exception as e:
        health['database'] = 'error'
        health['status'] = 'unhealthy'
    
    # Check cache
    try:
        cache.set('health_check', 'ok', 1)
        health['cache'] = 'ok'
    except Exception as e:
        health['cache'] = 'error'
    
    return JsonResponse(health)
```

---

## Monitoring Dashboard Metrics

### Key Metrics to Graph

1. **Database Metrics**
   - Connection count
   - Slow query count
   - Query latency
   - Cache hit ratio

2. **Application Metrics**
   - Request count
   - Error rate
   - Response time
   - Active users

3. **Infrastructure Metrics**
   - CPU usage
   - Memory usage
   - Disk I/O
   - Network I/O

4. **Business Metrics**
   - Streams started
   - Stream success rate
   - User signups
   - Revenue

---

## Backup & Recovery Strategy

### Daily Backup Script

```bash
#!/bin/bash

# Backup PostgreSQL
pg_dump -h $DB_HOST -U postgres youtubestreamer_prod | \
    gzip > /backups/db_$(date +%Y%m%d_%H%M%S).sql.gz

# Backup S3 bucket
aws s3 sync s3://yourbucket /backups/s3_backup/ \
    --region us-east-1

# Keep only last 7 days
find /backups -name "db_*.sql.gz" -mtime +7 -delete

# Upload to S3 (backup of backups)
aws s3 sync /backups s3://yourbucket-backups/ \
    --delete --region us-east-1

echo "Backup completed at $(date)" >> /var/log/backups.log
```

---

## Scaling Strategy

### Horizontal Scaling

1. **Load Balancing:** Use AWS ALB or Nginx
2. **Multiple Application Servers:** Run 2-4 instances
3. **Database Read Replicas:** For reporting queries
4. **Redis Sentinel:** For high availability

### Vertical Scaling

1. **Increase Database RAM:** For better caching
2. **Increase Instance Type:** For more CPU
3. **Increase Redis Memory:** For better cache hit rate

---

## Disaster Recovery Plan

### RTO/RPO Targets
- Recovery Time Objective (RTO): 1 hour
- Recovery Point Objective (RPO): 1 hour

### Failover Procedure

1. Monitor health checks continuously
2. If primary fails, switch to replica within 5 minutes
3. Notify team immediately
4. Begin post-incident review

### Testing Schedule

- Monthly: Failover drills
- Quarterly: Full disaster recovery test
- As-needed: After major changes

---

*Configuration Reference v1.0*
*Last Updated: 2024*
*For Production Use*
