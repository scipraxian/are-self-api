'''Application configuration for the dashboard app.'''

import os

from django.apps import AppConfig


class DashboardConfig(AppConfig):
  '''Dashboard configuration with startup task initialization.'''
  name = 'dashboard'

  def ready(self):
    '''Triggers initial network scan on server startup.'''
    # Only run in the main process, not the reloader thread
    if os.environ.get('RUN_MAIN') == 'true':
      try:
        from core.tasks import scan_network_task
        # Delay the task slightly to ensure Redis and Workers are ready
        scan_network_task.apply_async(countdown=5)
      except Exception as e:
        print(f'Startup Scan Error: {e}')
