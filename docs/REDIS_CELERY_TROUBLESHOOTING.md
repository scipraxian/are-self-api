# Redis / Celery Connection Troubleshooting

If the Celery worker reports **"Error 10061 connecting to localhost:6379. No connection could be made because the target machine actively refused it"**, follow these steps.

---

## Step 1: Confirm Redis is running

Nothing is listening on port 6379, so Redis is either not running or not bound to that port.

**Option A – You use Redis installed locally (e.g. MSI, Chocolatey):**

- Open **Services** (Win+R → `services.msc`) and look for **Redis**.
- If it’s **Stopped**, right‑click → **Start**.
- If there is no Redis service, Redis may be installed in WSL or Docker; use the steps below for that environment.

**Option B – You use WSL:**

```bash
wsl -e bash -c "redis-cli ping"
```

- If you get `PONG`, Redis is running in WSL. Go to **Step 3** (worker and Redis in different “machines”).
- If you get “connection refused” or “command not found”, start Redis in WSL:

```bash
wsl -e bash -c "sudo service redis-server start"
# or
wsl -e bash -c "sudo redis-server --daemonize yes"
```

**Option C – You use Docker:**

```powershell
docker ps
```

- Look for a container that runs Redis (image name often contains `redis`).
- If Redis is not running:

```powershell
docker run -d --name redis -p 6379:6379 redis:alpine
```

- If Redis runs in a container **without** `-p 6379:6379`, it is not exposed to the host. Either:
  - Publish the port and use `localhost:6379`, or
  - Run the Celery worker inside the same Docker network and use the Redis **container name** as host (see Step 3).

---

## Step 2: Check that port 6379 is listening

On **Windows (PowerShell)**:

```powershell
Get-NetTCPConnection -LocalPort 6379 -ErrorAction SilentlyContinue | Select-Object LocalAddress, LocalPort, State
```

- If you see **State = Listen**, something (usually Redis) is listening on 6379.
- If you get no rows, nothing is listening on 6379 → start or expose Redis (Step 1).

If Redis runs **inside WSL**, the above may show nothing on the Windows side. In WSL:

```bash
ss -tlnp | grep 6379
# or
netstat -tlnp | grep 6379
```

---

## Step 3: Use the correct broker URL

Talos reads the broker from the **CELERY_BROKER_URL** environment variable (if set), otherwise uses `redis://localhost:6379/`.

- **Redis on Windows (same machine as worker):**  
  `redis://localhost:6379/` is correct. Ensure Redis is started (Step 1).

- **Redis in WSL:**  
  From Windows, “localhost” usually reaches WSL2’s forwarded ports. If it still fails:
  - In WSL, ensure Redis is bound to `0.0.0.0` or `127.0.0.1` (default is often `127.0.0.1`).
  - Try explicitly:

  ```powershell
  $env:CELERY_BROKER_URL = "redis://127.0.0.1:6379/"
  celery -A config worker -l info
  ```

- **Redis in Docker (port 6379 published to host):**  
  Same as above: `redis://localhost:6379/` and ensure the container is running and the port is published.

- **Redis in Docker (worker also in Docker, same network):**  
  Use the Redis **service/container name** as host, e.g.:

  ```powershell
  $env:CELERY_BROKER_URL = "redis://redis:6379/"
  ```

Then start the worker (same host or inside Docker, as appropriate).

---

## Step 4: Test the broker URL before starting the worker

**From Windows (if `redis-cli` is on PATH or in WSL):**

```powershell
# If you have redis-cli (e.g. via WSL):
wsl -e redis-cli -h localhost -p 6379 ping
# Expect: PONG
```

**From Python (in your project venv):**

```powershell
cd c:\Users\scfre\CursorProjects\talos
python -c "
import os
url = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/')
print('Broker URL:', url)
try:
    import redis
    r = redis.from_url(url)
    r.ping()
    print('Redis PING: OK')
except Exception as e:
    print('Redis PING failed:', e)
"
```

If PING fails, fix Redis (Step 1) and/or the broker URL (Step 3) before starting the worker.

---

## Step 5: Start the worker with the chosen broker

After Redis is running and reachable:

```powershell
cd c:\Users\scfre\CursorProjects\talos
# Optional: set broker if not using default
# $env:CELERY_BROKER_URL = "redis://localhost:6379/"
celery -A config worker -l info
```

You should see the worker connect and list tasks instead of “Trying again in 4.00 seconds...”.

---

## Summary checklist

1. **Redis process** is running (Windows service, WSL, or Docker).
2. **Port 6379** is listening where the worker expects it (host or container).
3. **CELERY_BROKER_URL** points at that Redis (host/port or container name).
4. **Test** with `redis-cli ping` or the Python snippet above.
5. **Start** the worker with `celery -A config worker -l info`.

If your “local Redis hasn’t changed” but the worker still gets 10061, the most common cause is that the Redis **process** is no longer running (e.g. after a reboot or WSL/Docker restart). Re-run Step 1 and 2, then 4 and 5.
