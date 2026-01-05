'''Celery tasks for the dashboard application.'''

import time
from celery import shared_task


@shared_task
def debug_task():
  '''A simple placeholder Celery task.'''
  print('Build Started')
  time.sleep(5)
  print('Build Completed')
  return 'Task Finished'
