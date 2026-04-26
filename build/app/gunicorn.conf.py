# Copyright The IETF Trust 2024-2026, All Rights Reserved

# --- Version 25+ Specific Settings ---
# This disables the new interactive control socket
# and prevents [Errno 30] Read-only file system errors
control_socket_disable = True

# Log as JSON on stdout (to distinguish from Django's logs on stderr)
#
# This is applied as an update to gunicorn's glogging.CONFIG_DEFAULTS.
logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "root": {"level": "INFO", "handlers": ["console"]},
    "loggers": {
        "gunicorn.error": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
            "qualname": "gunicorn.error"
        },

        "gunicorn.access": {
            "level": "INFO",
            "handlers": ["access_console"],
            "propagate": False,
            "qualname": "gunicorn.access"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "stream": "ext://sys.stdout"
        },
        "access_console": {
            "class": "logging.StreamHandler",
            "formatter": "access_json",
            "stream": "ext://sys.stdout"
        },
    },
    "formatters": {
        "json": {
            "class": "mlarchive.utils.jsonlogger.MailArchiveJsonFormatter",
            "style": "{",
            "format": "{asctime}{levelname}{message}{name}{process}",
        },
        "access_json": {
            "class": "mlarchive.utils.jsonlogger.GunicornRequestJsonFormatter",
            "style": "{",
            "format": "{asctime}{levelname}{message}{name}{process}",
        }
    }
}