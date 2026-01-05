'''Views for the dashboard application.'''

from celery.result import AsyncResult
from django.http import HttpResponse
from django.shortcuts import render
from django.views import View
from django.views.generic import TemplateView

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
