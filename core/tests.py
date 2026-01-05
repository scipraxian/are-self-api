'''Tests for core utility functions.'''

from unittest.mock import patch
from django.test import TestCase
from core.utils.scanner import NetworkScanner

class ScannerTests(TestCase):
  '''Tests for the NetworkScanner utility.'''

  def setUp(self):
    self.scanner = NetworkScanner(timeout=0.1)

  @patch('socket.create_connection')
  @patch('os.path.exists')
  @patch('socket.gethostbyaddr')
  def test_check_agent_online(self, mock_gethost, mock_exists, mock_conn):
    '''Tests detection of an online agent with valid storage.'''
    # Mock socket connection and ping/pong
    mock_socket = mock_conn.return_value.__enter__.return_value
    mock_socket.recv.return_value = b'PONG'
    
    # Mock storage and hostname
    mock_exists.return_value = True
    mock_gethost.return_value = ['agent-01']
    
    result = self.scanner.check_agent('192.168.1.10')
    
    self.assertTrue(result['online'])
    self.assertTrue(result['share_ok'])
    self.assertEqual(result['hostname'], 'agent-01')

  @patch('socket.create_connection')
  def test_check_agent_offline(self, mock_conn):
    '''Tests detection of an offline agent.'''
    mock_conn.side_effect = ConnectionRefusedError()
    
    result = self.scanner.check_agent('192.168.1.11')
    
    self.assertFalse(result['online'])
    self.assertFalse(result['share_ok'])
