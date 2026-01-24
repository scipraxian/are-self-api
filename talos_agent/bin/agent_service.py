# DEPRECIATED
import json
import logging
import os
import socket
import subprocess
import threading
import time
import sys
from typing import Any, Dict, Optional

import psutil

VERSION = '2.1.6'


class TalosAgent:
    '''A flexible, socket-based agent for remote UE5 process management.'''

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
        info = {'path': path, 'exists': False, 'is_dir': False, 'writable': False, 'size': 0, 'error': None}
        if not path: return info

        try:
            if os.path.exists(path):
                info['exists'] = True
                info['is_dir'] = os.path.isdir(path)
                info['size'] = os.path.getsize(path) if not info['is_dir'] else 0
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
        except Exception as e:
            self.logger.error(f"Probe exception for {path}: {e}")
            info['error'] = str(e)

        return info

    def handle_request(self, conn: socket.socket, addr: tuple):
        try:
            data = conn.recv(65536).decode('utf-8').strip()
            if not data: return

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

            elif cmd == 'LIST_LOGS':
                log_dir = args.get('log_dir')
                if not log_dir or not os.path.exists(log_dir):
                    res['status'] = 'ERROR'
                    res['message'] = f'Log directory not found: {log_dir}'
                else:
                    try:
                        logs = [f for f in os.listdir(log_dir) if f.endswith('.log')]
                        logs.sort()
                        res['data'] = logs
                    except Exception as e:
                        res['status'] = 'ERROR'
                        res['message'] = str(e)

            elif cmd == 'STATUS':
                pname = args.get('process_name')
                proc = self._get_proc_by_name(pname) if pname else None
                metrics = {'cpu': 0, 'ram_mb': 0, 'alive': False, 'functioning': False}
                if proc:
                    try:
                        metrics['alive'] = True
                        metrics['cpu'] = proc.cpu_percent()
                        metrics['ram_mb'] = proc.memory_info().rss / (1024 * 1024)
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
                    if '-AutoStart' not in params: params.append('-AutoStart')

                    self.logger.info(f"Launching {exe} with {params}")
                    subprocess.Popen(
                        [exe] + params,
                        creationflags=(subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
                    )
                    res['status'] = 'LAUNCHED'
                else:
                    res['status'] = 'ERROR'
                    res['message'] = f'Executable not found: {exe}'

            elif cmd == 'KILL':
                pname = args.get('process_name')
                if not pname.endswith('.exe'): pname += '.exe'

                proc = self._get_proc_by_name(pname)
                if not proc:
                    res['status'] = 'NOT_FOUND'
                else:
                    self.logger.info(f"Killing {pname}...")
                    subprocess.run(f'taskkill /IM {pname}', shell=True, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)

                    time.sleep(0.5)
                    proc = self._get_proc_by_name(pname)
                    if proc:
                        proc.kill()

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
                    target_file = os.path.abspath(__file__)
                    with open(target_file, 'w') as f:
                        f.write(content)
                    res['status'] = 'UPDATING'
                    conn.sendall((json.dumps(res) + '\n').encode('utf-8'))
                    conn.close()

                    bat_path = os.path.join(os.path.dirname(target_file), "_restart.bat")
                    with open(bat_path, 'w') as f:
                        f.write(f'@echo off\ncd /d "%~dp0"\ntimeout /t 1\n"{sys.executable}" "{target_file}"\ndel %0\n')

                    subprocess.Popen([bat_path], shell=True,
                                     creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS)
                    os._exit(0)
                else:
                    res['status'] = 'INVALID_CONTENT'

            elif cmd == 'ATTACH_LOGS':
                # NEW: Hand off control to the streaming loop
                self._stream_logs(conn, args.get('log_path'))
                return

            else:
                res['status'] = 'ERROR'
                res['message'] = f'Unknown command: {cmd}'

            response_data = (json.dumps(res) + '\n').encode('utf-8')
            conn.sendall(response_data)

        except Exception as e:
            self.logger.error('Handler error: %s', e)
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _stream_logs(self, conn: socket.socket, path: str):
        """
    Stateful Loop: Waits for file, then tails it byte-by-byte.
    Pushes JSON lines to the socket.
    """
        self.logger.info(f"Starting log stream for: {path}")

        # 1. Wait for file creation (up to 10s)
        wait_start = time.time()
        while not os.path.exists(path):
            if time.time() - wait_start > 10.0:
                msg = json.dumps({'type': 'error', 'content': f'Log creation timed out: {path}'}) + '\n'
                try:
                    conn.sendall(msg.encode('utf-8'))
                except:
                    pass
                return
            time.sleep(0.5)

        # 2. Open and Stream
        try:
            with open(path, 'r', errors='ignore') as f:
                # DO NOT SEEK END. Read from 0 to capture startup.
                while self.running:
                    line = f.readline()
                    if line:
                        payload = json.dumps({'type': 'log', 'content': line.strip()})
                        conn.sendall((payload + '\n').encode('utf-8'))
                    else:
                        # EOF reached, wait for more data
                        time.sleep(0.1)

        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
            self.logger.info("Log stream client disconnected.")
        except Exception as e:
            self.logger.error(f"Stream crash: {e}")

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