# celery_app.py 

from celery import Celery
import os

# Initialize the Celery app
celery_app = Celery(
    'celery_app',
    broker='amqps://btwzozrv:pcIervFsmCoKgcB2KtOSdNNHMJD7qWRJ@octopus.rmq3.cloudamqp.com/btwzozrv',
    backend='redis://localhost:6380/0',  # Memurai instance as backend on port 6380
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],  # Accept only JSON content
)

# Optional: Load configuration from a separate config file or object
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],  # Specify content types to accept
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

# Import tasks to register them with Celery (THIS WORKS!!!)
import tasks.generate_tasks

# # Optional: ASK GPT ABOUT IT'S PURPOSE: Automatically discover tasks in specified modules
# # This allows Celery to find tasks in modules like `generate_tasks.py` and `other_tasks.py`

celery_app.autodiscover_tasks(['tasks'])
celery_app.autodiscover_tasks(['tasks.generate_tasks'])

# Sanity check print statement
print("Registered tasks:")
print(celery_app.tasks.keys())
print(" ")