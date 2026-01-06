'''Tests for the dashboard application.'''

from unittest.mock import MagicMock
from unittest.mock import patch

from django.test import Client
from django.test import TestCase
from django.urls import reverse

from dashboard.tasks import debug_task


class DashboardViewTests(TestCase):
  '''Tests for the dashboard views.'''

  def setUp(self):
    '''Initializes the test client.'''
    self.client = Client()

  def test_home_view(self):
    '''Test that the home page loads correctly.'''
    response = self.client.get(reverse('home'))
    self.assertEqual(response.status_code, 200)
    self.assertTemplateUsed(response, 'dashboard/home.html')
    self.assertContains(response, 'Talos Command Center')
    # CHANGED: Look for the new "Sonar" header instead of the old button
    self.assertContains(response, 'Sonar: Build Agents')

  @patch('dashboard.views.debug_task.delay')
  def test_trigger_build_post(self, mock_task_delay):
    '''Test that POSTing to trigger_build starts the task and returns HTMX.'''
    # Mock the task to return a fixed ID
    mock_task = MagicMock()
    mock_task.id = 'test-task-123'
    mock_task_delay.return_value = mock_task

    response = self.client.post(reverse('trigger_build'))

    # Check task was triggered
    mock_task_delay.assert_called_once()

    # Check response contains polling logic and task ID
    self.assertEqual(response.status_code, 200)
    content = response.content.decode()
    self.assertIn('Build Queued...', content)
    self.assertIn('hx-get="/check-status/test-task-123/"', content)
    self.assertIn('hx-trigger="every 2s"', content)

  def test_trigger_build_get_not_allowed(self):
    '''Test that GET requests to trigger_build are rejected.'''
    response = self.client.get(reverse('trigger_build'))
    self.assertEqual(response.status_code, 405)

  @patch('dashboard.views.AsyncResult')
  def test_check_status_pending(self, mock_async_result):
    '''Test status check when task is still running.'''
    # Mock task not ready
    mock_result = MagicMock()
    mock_result.ready.return_value = False
    mock_async_result.return_value = mock_result

    url = reverse('check_build_status', kwargs={'task_id': 'test-id'})
    response = self.client.get(url)

    self.assertEqual(response.status_code, 200)
    self.assertIn('Build Queued...', response.content.decode())
    self.assertIn('hx-trigger="every 2s"', response.content.decode())

  @patch('dashboard.views.AsyncResult')
  def test_check_status_finished(self, mock_async_result):
    '''Test status check when task is completed.'''
    # Mock task ready
    mock_result = MagicMock()
    mock_result.ready.return_value = True
    mock_async_result.return_value = mock_result

    url = reverse('check_build_status', kwargs={'task_id': 'test-id'})
    response = self.client.get(url)

    self.assertEqual(response.status_code, 200)
    self.assertIn('Execute Build', response.content.decode())
    self.assertNotIn('disabled', response.content.decode())
    self.assertNotIn('hx-trigger', response.content.decode())

  @patch('dashboard.views.celery_app.control.shutdown')
  @patch('dashboard.views.os._exit')
  def test_shutdown_post(self, mock_exit, mock_celery_shutdown):
    '''Test that POSTing to shutdown triggers Celery and Django exit.'''
    response = self.client.post(reverse('shutdown'))
    self.assertEqual(response.status_code, 200)
    
    # Verify Celery shutdown was signaled
    mock_celery_shutdown.assert_called_once()
    
    # Verify Django process exit
    mock_exit.assert_called_once_with(0)


class DashboardTaskTests(TestCase):
  '''Tests for the dashboard tasks.'''

  def test_debug_task_execution(self):
    '''Test the Celery task directly.'''
    # For unit testing the logic inside the task
    result = debug_task.apply()  # apply() runs it synchronously
    self.assertEqual(result.result, 'Task Finished')
    self.assertTrue(result.successful())


class DashboardBrokerTests(TestCase):
  '''Verifies connection to the message broker.'''

  def test_broker_connection(self):
    '''Verifies that Celery can connect to the configured broker (Redis).'''
    from config.celery import app as celery_app
    try:
      with celery_app.connection() as connection:
        connection.connect()
        self.assertTrue(connection.connected)
    except Exception as e:
      self.fail(f'Celery could not connect to the broker: {e}')
