'''Verification script to test Redis and Celery connection.'''

import sys
import os
import django

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from config.celery import app as celery_app
from dashboard.tasks import debug_task

def verify_connection():
  '''Tests connection to Redis and triggers a trial task.'''
  print('--- Talos Async Verification ---')
  
  # 1. Test Redis Connection
  try:
    print('Testing Redis connection...')
    celery_app.connection().connect()
    print('SUCCESS: Connected to Redis.')
  except Exception as e:
    print(f'FAILURE: Could not connect to Redis: {e}')
    return

  # 2. Trigger Task (Async)
  print('Triggering debug_task...')
  result = debug_task.delay()
  print(f'Task triggered successfully. Task ID: {result.id}')
  print('Note: Ensure your worker is running (talos.bat) to see "Build Started" in the worker logs.')
  print('--------------------------------')

if __name__ == '__main__':
  verify_connection()
