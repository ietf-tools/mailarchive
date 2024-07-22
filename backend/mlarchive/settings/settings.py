# settings/settings.py
from .base import *

# Console logs as JSON instead of plain when running in k8s
LOGGING["handlers"]["console"]["formatter"] = "json"
