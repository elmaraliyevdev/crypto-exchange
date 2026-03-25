"""Celery application factory, broker/backend configuration, and task discovery."""

from celery import Celery

from app.core.config import settings

broker_url = settings.CELERY_BROKER_URL or settings.REDIS_URL
result_backend = settings.CELERY_RESULT_BACKEND or settings.REDIS_URL

celery_app = Celery(
    "crypto_exchange",
    broker=broker_url,
    backend=result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)

# Ensure tasks are registered when the worker imports the app.
from app.tasks import matching_engine  # noqa: F401
