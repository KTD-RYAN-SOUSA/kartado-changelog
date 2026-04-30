"""
Configuração de Logging para Django ECS Fargate
"""
import os
import sys


# Filtro customizado para ignorar health checks
class IgnoreHealthCheckFilter:
    """
    Filtro para remover logs de health checks (/health/)
    Funciona com Django e Gunicorn
    """

    def filter(self, record):
        message = record.getMessage()
        # Ignora qualquer log que contenha /health/
        if "/health/" in message:
            return False
        # Ignora logs de health check do curl
        if "GET /health/" in message or "POST /health/" in message:
            return False
        return True


# Nível de log baseado no ambiente
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{levelname}] {asctime} {name} - {message}",
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "simple": {
            "format": "[{levelname}] {message}",
            "style": "{",
        },
    },
    "filters": {
        # Filtro para ignorar health checks nos logs
        "ignore_health_checks": {
            "()": "RoadLabsAPI.settings.logging_config.IgnoreHealthCheckFilter",
        },
    },
    "handlers": {
        "console": {
            "level": LOG_LEVEL,
            "class": "logging.StreamHandler",
            "stream": sys.stdout,  # Força saída para stdout (CloudWatch)
            "formatter": "verbose",
            "filters": ["ignore_health_checks"],
        },
        "console_simple": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "formatter": "simple",
            "filters": ["ignore_health_checks"],
        },
    },
    "loggers": {
        # Logger principal do Django
        "django": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        # Requests HTTP (sem health checks)
        "django.request": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        # Queries SQL (útil em DEBUG)
        "django.db.backends": {
            "handlers": ["console_simple"],
            "level": "DEBUG" if LOG_LEVEL == "DEBUG" else "WARNING",
            "propagate": False,
        },
        # Server (runserver, gunicorn logs)
        "django.server": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        # Logger customizado para apps
        "apps": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        # Gunicorn access logs (sem health checks)
        "gunicorn.access": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        # Gunicorn error logs
        "gunicorn.error": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
}
