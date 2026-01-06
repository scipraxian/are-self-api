'''Talos Remote Agent v2.1
Dumb Remote Execution Service. Stateless and variable-driven.
'''

import json
import logging
import os
import socket
import subprocess
import threading
import time
import traceback
import sys
from datetime import datetime
from typing import Any, Dict, Optional

import psutil

from talos_agent.version import VERSION

class TalosAgent:
  '''A flexible, socket-based agent for remote UE5 process management.
     Accepts all paths and configurations from the controller.
  '''

  def __init__(self, port: int = 5005):
    self.port = port
    self.logger = self._setup_logging()
    self.running = True

  def _setup_logging(self):
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    )
    return logging.getLogger('TalosAgent')

  def _get_proc_by_name(self, name: str) -> Optional[psutil.Process]:
    '''Finds a process by name or partial name.'''
    try:
      for proc in psutil.process_iter(['name', 'exe']):
        try:
          pname = proc.info.get('name')
          if not pname: continue
          if name.lower() in pname.lower():
            return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
          continue
    except Exception as e:
      self.logger.error('Process iteration failure: %s', e)
    return None

  def _probe_path(self, path: str) -> Dict[str, Any]:
    '''Checks if a path exists and returns its metadata.'''
    info = {'path': path, 'exists': False, 'is_dir': False, 'writable': False, 'size': 0, 'error': None}
    if not path: return info
    
    try:
      if os.path.exists(path):
        info['exists'] = True
        info['is_dir'] = os.path.isdir(path)
        info['size'] = os.path.getsize(path) if not info['is_dir'] else 0
        
        # Check writability
        if info['is_dir']:
          try:
            test_file = os.path.join(path, '.talos_probe')
            with open(test_file, 'w') as f:
              f.write('t')
            os.remove(test_file)
            info['writable'] = True
          except Exception as e:
            info['writable'] = False
            info['error'] = f"Writability check failed: {e}"
        else:
          info['writable'] = os.access(path, os.W_OK)
      else:
        self.logger.warning(f"Probe failed: Path does not exist: {path}")
        info['error'] = "Path not found"
    except Exception as e:
      self.logger.error(f"Probe exception for {path}: {e}")
      info['error'] = str(e)
        
    return info

  def handle_request(self, conn: socket.socket, addr: tuple):
    '''Main command dispatcher.'''
    try:
      data = conn.recv(65536).decode('utf-8').strip()
      if not data: return

      # Support legacy/simple PING
      if data == 'PING':
        conn.sendall(b'PONG')
        return

      try:
        req = json.loads(data)
      except json.JSONDecodeError:
        self.logger.error('Invalid JSON from %s', addr[0])
        return

      cmd = req.get('cmd', '').upper()
      args = req.get('args', {})
      
      self.logger.info(f"REQUEST [{cmd}] from {addr[0]}")
      
      res = {'status': 'OK', 'version': VERSION, 'hostname': socket.gethostname()}

      if cmd == 'PING':
        res['status'] = 'PONG'

      elif cmd == 'PROBE':
        res['data'] = self._probe_path(args.get('path'))

      elif cmd == 'STATUS':
        pname = args.get('process_name')
        proc = self._get_proc_by_name(pname) if pname else None
        metrics = {'cpu': 0, 'ram_mb': 0, 'alive': False, 'functioning': False}
        if proc:
          try:
            metrics['alive'] = True
            metrics['cpu'] = proc.cpu_percent()
            metrics['ram_mb'] = proc.memory_info().rss / (1024*1024)
            metrics['pid'] = proc.pid
            lp = args.get('log_path')
            if lp and os.path.exists(lp):
              metrics['functioning'] = (time.time() - os.path.getmtime(lp)) < 60
            else:
              metrics['functioning'] = proc.status() != psutil.STATUS_ZOMBIE
          except (psutil.NoSuchProcess, psutil.AccessDenied):
            metrics['alive'] = False
        res['data'] = metrics

      elif cmd == 'LAUNCH':
        exe = args.get('exe_path')
        if exe and os.path.exists(exe):
          params = args.get('params', [])
          # Default UE5 flags if not specified
          if '-AutoStart' not in params: params.append('-AutoStart')
          
          self.logger.info(f"Launching {exe} with {params}")
          subprocess.Popen(
              [exe] + params,
              creationflags=(
                  subprocess.DETACHED_PROCESS |
                  subprocess.CREATE_NEW_PROCESS_GROUP
              )
          )
          res['status'] = 'LAUNCHED'
        else:
          res['status'] = 'ERROR'
          res['message'] = f'Executable not found: {exe}'

      elif cmd == 'KILL':
        pname = args.get('process_name')
        if not pname.endswith('.exe'): pname += '.exe'
        
        # Check existence first
        proc = self._get_proc_by_name(pname)
        if not proc:
          res['status'] = 'NOT_FOUND'
        else:
          self.logger.info(f"Requesting Graceful Exit for {pname}...")
          # 1. Graceful attempt via taskkill
          subprocess.run(
              f'taskkill /IM {pname}',
              shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
          )
          
          # 2. Wait up to 5 seconds
          killed = False
          for _ in range(5):
            if not self._get_proc_by_name(pname):
              killed = True
              break
            time.sleep(1)
            
          if not killed:
            self.logger.warning(f"Graceful exit timed out for {pname}. Force killing.")
            # Refetch in case it changed
            proc = self._get_proc_by_name(pname)
            if proc:
              proc.kill()
              killed = True
              
          res['status'] = 'KILLED'

      elif cmd == 'TAIL':
        path = args.get('log_path')
        n = args.get('lines', 50)
        if path and os.path.exists(path):
          try:
            with open(path, 'r', errors='ignore') as f:
              content = f.readlines()
              res['data'] = content[-n:]
          except Exception as e:
            res['status'] = 'ERROR'
            res['message'] = str(e)
        else:
          res['status'] = 'NOT_FOUND'

      elif cmd == 'UPDATE_SELF':
        content = args.get('content')
        if content and 'Talos Remote Agent' in content:
            self.logger.info("Received update payload. Updating...")
            try:
                target_file = os.path.abspath(__file__)
                with open(target_file, 'w') as f: f.write(content)
                res['status'] = 'UPDATING'
                conn.sendall((json.dumps(res) + '\n').encode('utf-8'))
                conn.close()
                self.logger.info("Restarting agent...")
                time.sleep(1)
                # On Windows, os.execv can sometimes fail to restart from certain parent processes.
                # Using Popen with NEW_CONSOLE is more robust for standalone agents.
                subprocess.Popen(
                    [sys.executable, target_file],
                    creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS
                )
            except Exception as e:
                res['status'] = 'ERROR'
                res['message'] = str(e)
        else:
            res['status'] = 'INVALID_CONTENT'

      elif cmd == 'ATTACH_LOGS':
        self._stream_logs(conn, args.get('log_path'))
        return

      else:
        self.logger.warning(f"Unknown command received: {cmd}")
        res['status'] = 'ERROR'
        res['message'] = f'Unknown command: {cmd}'

      # Send Response
      if cmd != 'UPDATE_SELF':
          response_data = (json.dumps(res) + '\n').encode('utf-8')
          conn.sendall(response_data)
      else:
          # For UPDATE_SELF, we've already sent the response and closed.
          # We must now kill the process so the Popen'd child can take over.
          self.logger.info("Agent process exiting for update.")
          os._exit(0)

    except Exception as e:
      self.logger.error('Handler error: %s\n%s', e, traceback.format_exc())
    finally:
      try: conn.close()
      except OSError: pass

  def _stream_logs(self, conn: socket.socket, path: str):
    if not path or not os.path.exists(path):
      conn.sendall(json.dumps({'type': 'error', 'content': 'Log not found'}).encode() + b'\n')
      return

    self.logger.info('Streaming: %s', path)
    with open(path, 'r', errors='ignore') as f:
      f.seek(0, os.SEEK_END)
      while self.running:
        line = f.readline()
        if line:
          payload = json.dumps({'type': 'log', 'content': line.strip()})
          conn.sendall((payload + '\n').encode('utf-8'))
        else:
          time.sleep(0.1)

  def run(self):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
      s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
      s.bind(('0.0.0.0', self.port))
      s.listen(10)
      self.logger.info('TALOS AGENT v%s ONLINE on %d', VERSION, self.port)
      while self.running:
        conn, addr = s.accept()
        threading.Thread(target=self.handle_request, args=(conn, addr), daemon=True).start()

if __name__ == '__main__':
  TalosAgent().run()
