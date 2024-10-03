from celery import Celery
import os

# Initialize the Celery app
celery_app = Celery(
    'tasks',  # Name of the Celery application
    broker=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),  # Broker URL (e.g., Redis)
    backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')  # Result backend
)

# Optional: Load configuration from a separate config file or object
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],  # Specify content types to accept
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

# Optional: ASK GPT ABOUT IT'S PURPOSE: Automatically discover tasks in specified modules
# This allows Celery to find tasks in modules like `generate_tasks.py` and `other_tasks.py`

# celery_app.autodiscover_tasks(['tasks.generate_tasks', 'tasks.other_tasks'])