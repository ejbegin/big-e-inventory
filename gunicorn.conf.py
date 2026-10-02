import os

# Gunicorn configuration automatically loaded by Gunicorn
timeout = 120
workers = int(os.environ.get('WEB_CONCURRENCY', 2))
threads = 2
keepalive = 5
