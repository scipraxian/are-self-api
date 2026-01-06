'''Network scanning utility for detecting Talos build agents.'''

import concurrent.futures
import json
import os
import socket


class NetworkScanner:
  '''Handles network-wide agent discovery and status verification.'''

  def __init__(self, port=5005, timeout=0.5):
    self.port = port
    self.timeout = timeout

  def get_local_subnet(self):
    '''Returns the local subnet string (e.g., "192.168.1.").'''
    try:
      # Connect to an external address to find the local IP
      s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
      s.connect(('8.8.8.8', 80))
      local_ip = s.getsockname()[0]
      s.close()
      return '.'.join(local_ip.split('.')[:-1]) + '.'
    except Exception:
      return '127.0.0.'

  def check_agent(self, ip):
    '''Verifies if an agent is active and has valid storage access.

    Returns:
        dict: {'hostname': str, 'ip': str, 'online': bool, 'share_ok': bool}
    '''
    result = {
        'hostname': 'Unknown',
        'ip': ip,
        'online': False,
        'share_ok': False
    }

    try:
      # Try modern JSON PING first, fallback to raw if needed (though agent handles both)
      with socket.create_connection((ip, self.port), timeout=self.timeout) as s:
        # Sending modern JSON PING
        payload = json.dumps({'cmd': 'PING'}).encode('utf-8')
        s.sendall(payload)
        
        raw_response = s.recv(1024).decode('utf-8').strip()
        
        # Check for JSON PONG or raw PONG
        is_pong = False
        if raw_response == 'PONG':
          is_pong = True
        else:
          try:
            res_json = json.loads(raw_response)
            if res_json.get('status') == 'PONG':
              is_pong = True
          except json.JSONDecodeError:
            pass

        if is_pong:
          result['online'] = True
          try:
            result['hostname'] = socket.gethostbyaddr(ip)[0]
          except Exception:
            result['hostname'] = ip

          # 2. Storage Check
          share_path = fr'\\{ip}\steambuild'
          if os.path.exists(share_path):
            result['share_ok'] = True
    except (socket.timeout, ConnectionRefusedError, OSError):
      pass
    except Exception:
      # Catch-all for scanner robustness
      pass

    return result

  def scan_subnet(self):
    '''Scans the local subnet for active agents using thread pool.'''
    subnet = self.get_local_subnet()
    ips = [f'{subnet}{i}' for i in range(1, 255)]
    agents = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
      future_to_ip = {executor.submit(self.check_agent, ip): ip for ip in ips}
      for future in concurrent.futures.as_completed(future_to_ip):
        try:
          res = future.result()
          if res['online']:
            agents.append(res)
        except Exception:
          pass

    return agents
