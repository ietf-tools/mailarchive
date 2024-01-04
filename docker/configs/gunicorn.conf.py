import multiprocessing

bind = "0.0.0.0:8000"
workers = multiprocessing.cpu_count() * 2 + 1
max_requests = 32768
timeout = 180

# Logging settings
errorlog = "/data/log/gunicorn_error.log"
accesslog = "/data/log/gunicorn_access.log"
loglevel = "info"