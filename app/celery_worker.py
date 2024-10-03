from main import celery_app

# Start the Celery worker
if __name__ == "__main__":
    celery_app.worker_main()
