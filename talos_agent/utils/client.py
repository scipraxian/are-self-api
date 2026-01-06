'''Talos Agent Client: Interface for communicating with remote Talos Agents.'''

import json
import socket
import logging

class TalosAgentClient:
  '''Handles the protocol-level communication with a remote Talos Agent.'''

  def __init__(self, host: str, port: int = 5005, timeout: float = 2.0):
    self.host = host
    self.port = port
    self.timeout = timeout
    self.logger = logging.getLogger(f'TalosClient[{host}]')

  def _send_command(self, cmd: str, args: dict = None) -> dict:
    '''Encapsulates the JSON request/call-response cycle.'''
    payload = {
        'cmd': cmd,
        'args': args or {}
    }
    
    try:
      with socket.create_connection((self.host, self.port), timeout=self.timeout) as s:
        json_payload = json.dumps(payload) + '\n'
        print(f"[CLIENT] Sending to {self.host}:{self.port} -> {json_payload.strip()}")
        s.sendall(json_payload.encode('utf-8'))
        
        buffer = b''
        while True:
          chunk = s.recv(4096)
          if not chunk: break
          buffer += chunk
          if b'\n' in buffer: break
            
        data = buffer.decode('utf-8').strip()
        print(f"[CLIENT] Received from {self.host}:{self.port} <- {data}")
        
        if data == 'PONG': return {'status': 'PONG'}
        return json.loads(data)
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
      print(f"[CLIENT] ERROR: Connection failed to {self.host}:{self.port} - {e}")
      return {'status': 'ERROR', 'message': str(e)}
    except json.JSONDecodeError as e:
      print(f"[CLIENT] ERROR: Failed to parse JSON from {self.host}:{self.port} - {data}")
      return {'status': 'ERROR', 'message': f'Protocol error: {e}'}

  def ping(self) -> bool:
    res = self._send_command('PING')
    return res.get('status') == 'PONG'

  def probe_path(self, path: str) -> dict:
    '''Asks the agent if a path exists and its properties.'''
    return self._send_command('PROBE', {'path': path})

  def get_status(self, process_name: str, log_path: str = None) -> dict:
    '''Queries process metrics and health.'''
    return self._send_command('STATUS', {'process_name': process_name, 'log_path': log_path})

  def launch(self, exe_path: str, params: list = None) -> dict:
    return self._send_command('LAUNCH', {'exe_path': exe_path, 'params': params or []})

  def kill(self, process_name: str) -> dict:
    return self._send_command('KILL', {'process_name': process_name})

  def tail(self, log_path: str, lines: int = 50) -> dict:
    return self._send_command('TAIL', {'log_path': log_path, 'lines': lines})

  def list_logs(self, log_dir: str) -> dict:
    return self._send_command('LIST_LOGS', {'log_dir': log_dir})

  def update_agent(self, content: str) -> dict:
    '''Transmits new source code to the agent.'''
    return self._send_command('UPDATE_SELF', {'content': content})

  def stream_logs(self, log_path: str):
    '''Generator for log lines.'''
    payload = {'cmd': 'ATTACH_LOGS', 'args': {'log_path': log_path}}
    try:
      with socket.create_connection((self.host, self.port), timeout=None) as s:
        s.sendall((json.dumps(payload) + '\n').encode('utf-8'))
        buffer = ''
        while True:
          chunk = s.recv(4096).decode('utf-8', errors='ignore')
          if not chunk: break
          buffer += chunk
          while '\n' in buffer:
            line_str, buffer = buffer.split('\n', 1)
            line_str = line_str.strip()
            if not line_str: continue
            try:
                line_data = json.loads(line_str)
                if line_data.get('type') == 'log':
                    yield line_data.get('content')
            except json.JSONDecodeError:
                continue
    except Exception:
      pass
