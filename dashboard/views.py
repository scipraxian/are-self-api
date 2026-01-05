'''Views for the dashboard application.'''

import os

from celery.result import AsyncResult
from django.http import HttpResponse
from django.shortcuts import render
from django.views import View
from django.views.generic import TemplateView

from config.celery import app as celery_app
from dashboard.tasks import debug_task


class DashboardHomeView(TemplateView):
  '''Renders the main dashboard page.'''
  template_name = 'dashboard/home.html'


class TriggerBuildView(View):
  '''Triggers a Celery task and returns an HTML fragment.'''

  def post(self, request, *args, **kwargs):
    '''Handles POST requests to trigger a build.'''
    # Trigger the Celery task
    task = debug_task.delay()

    # Return the "Running..." state fragment with the task ID for polling
    return render(
        request,
        'dashboard/partials/build_button_queued.html',
        {'task_id': task.id},
    )


class BuildStatusView(View):
  '''Checks the status of a Celery task and returns appropriate HTML.'''

  def get(self, request, task_id, *args, **kwargs):
    '''Returns idle button if task is ready, else continues polling.'''
    result = AsyncResult(task_id)
    if result.ready():
      return render(request, 'dashboard/partials/build_button_idle.html')

    # Still running, return the queued button again to continue polling
    return render(
        request,
        'dashboard/partials/build_button_queued.html',
        {'task_id': task_id},
    )


class ShutdownView(View):
  '''System-wide shutdown for all Talos processes.

  This view is responsible for orchestrating a clean exit of the entire
  application stack, including:
  1. Signaling all Celery workers and agents to terminate.
  2. Shutting down the Django ASGI/HTTP server process.
  
  This is intended to be the single point of termination for the orchestrator.
  '''

  def post(self, request, *args, **kwargs):
    '''Triggers system-wide shutdown.'''
    print('System-wide shutdown initiated from dashboard...')
    
    # 1. Signaling Celery workers to shut down.
    # We use a broad ignore_result=True broadcast to stop all connected workers.
    try:
      celery_app.control.shutdown()
      print('Celery shutdown signal broadcasted successfully.')
    except Exception as e:
      print(f'Warning: Could not broadcast Celery shutdown: {e}')

    # 2. Exiting current Django process.
    # We use os._exit(0) to ensure the process terminates immediately 
    # and definitively in the development environment.
    print('Exiting Django server. Talos is now offline.')
    os._exit(0)
    return HttpResponse('System Offline')
