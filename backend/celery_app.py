import os
from celery import Celery

# Получаем настройки Redis
broker_url = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/0")

# --- ВАЖНОЕ ИСПРАВЛЕНИЕ: include=['tasks'] ---
# Мы явно говорим Celery: "При запуске загрузи файл tasks.py, там лежат функции"
app = Celery("ai_lawyer", broker=broker_url, backend=result_backend, include=["tasks"])

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,
    # Опционально: Если задача упала, не отправлять результат клиенту вечно
    task_track_started=True,
    task_time_limit=3000,  # 50 минут лимит на задачу (для длинных фильмов)
)
