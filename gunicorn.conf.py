import os

# Gunicorn configuration automatically loaded by Gunicorn
timeout = 120
workers = int(os.environ.get('WEB_CONCURRENCY', 2))
threads = 2
keepalive = 5
bind = f"0.0.0.0:{os.environ.get('PORT', '8085')}"

