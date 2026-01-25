'''Comprehensive tests for Talos Agent v2.1.0 communication and Discovery Logic.'''

import json
import socket
import threading
import time
import os
from unittest.mock import MagicMock, patch

from django.test import TestCase
from core.models import RemoteTarget
from core.tasks import discover_agent_assets_task
from talos_agent.bin.agent_service import TalosAgent
from talos_agent.utils.client import TalosAgentClient


class AgentDiscoveryTests(TestCase):
  '''Tests the network protocol and automated discovery of project assets.'''

  @classmethod
  def setUpClass(cls):
    super().setUpClass()
    cls.test_port = 5007
    cls.agent = TalosAgent(port=cls.test_port)
    cls.agent_thread = threading.Thread(target=cls.agent.run, daemon=True)
    cls.agent_thread.start()
    time.sleep(0.5)

  def setUp(self):
    self.target = RemoteTarget.objects.create(
        hostname='TEST-HOST',
        ip_address='127.0.0.1',
        agent_port=self.test_port,
        remote_build_path='/tmp/talos_test'
    )

  def test_probe_command(self):
    '''Verifies that the agent can probe its own directory.'''
    client = TalosAgentClient('127.0.0.1', port=self.test_port)
    res = client.probe_path(os.getcwd())
    data = res.get('data', {})
    self.assertTrue(data.get('exists'))
    self.assertTrue(data.get('is_dir'))

  def test_tail_command(self):
    '''Verifies that the agent can read the end of a file.'''
    test_file = 'test_tail.txt'
    with open(test_file, 'w') as f:
      for i in range(100):
        f.write(f"Line {i}\n")
    
    try:
      client = TalosAgentClient('127.0.0.1', port=self.test_port)
      res = client.tail(os.path.abspath(test_file), lines=5)
      lines = res.get('data', [])
      self.assertEqual(len(lines), 5)
      self.assertIn('Line 99\n', lines)
    finally:
      if os.path.exists(test_file):
        os.remove(test_file)

  def test_discovery_task(self):
    '''Verifies the asset discovery workflow.'''
    from environments.models import ProjectEnvironment
    
    # Create an active project environment for the test
    ProjectEnvironment.objects.all().delete() # Clear existing
    env = ProjectEnvironment.objects.create(
        name="Test Env",
        is_active=True,
        project_name='TalosTest',
        build_root=os.getcwd().replace('\\', '/')
    )
    
    self.target.remote_build_path = env.build_root
    self.target.save()
    
    # We'll create a dummy exe file to discover in the exact legacy location
    # Structure: [BuildRoot]/ReleaseTest/[ProjectName].exe
    exe_dir = os.path.join(os.getcwd(), 'ReleaseTest')
    os.makedirs(exe_dir, exist_ok=True)
    exe_path = os.path.join(exe_dir, 'TalosTest.exe')
    with open(exe_path, 'w') as f: f.write('dummy-exe')

    try:
      # Run discovery
      result = discover_agent_assets_task(self.target.id)
      
      self.target.refresh_from_db()
      self.assertTrue(self.target.is_exe_available)
      self.assertIn('ReleaseTest/TalosTest.exe', self.target.remote_exe_path.replace('\\', '/'))
    finally:
      # Cleanup
      import shutil
      shutil.rmtree(os.path.join(os.getcwd(), 'ReleaseTest'), ignore_errors=True)

  def test_status_command_with_log_heartbeat(self):
    '''Verifies that the agent uses log mtime for health metrics.'''
    log_file = 'heartbeat.log'
    with open(log_file, 'w') as f: f.write('log line')
    
    client = TalosAgentClient('127.0.0.1', port=self.test_port)
    
    # Case 1: Active log (just created)
    res = client.get_status(process_name='python', log_path=os.path.abspath(log_file))
    # We mock 'python' as the process name since it's definitely running during test
    self.assertTrue(res.get('data', {}).get('functioning'))
    
    # Case 2: Old log
    old_time = time.time() - 3600
    os.utime(log_file, (old_time, old_time))
    res = client.get_status(process_name='python', log_path=os.path.abspath(log_file))
    self.assertFalse(res.get('data', {}).get('functioning'))
    
    os.remove(log_file)
