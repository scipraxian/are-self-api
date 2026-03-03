---
description: Standards for developing and updating Talos Remote Agents
---

# Peripheral Nervous System Standards

The `peripheral_nervous_system/bin/agent_service.py` is a standalone script that is often deployed to remote machines where the full `talos` package is NOT installed. 

## 1. Versioning
- **CRITICAL**: The `VERSION` variable MUST be hardcoded within `agent_service.py`.
- **DO NOT** use `from peripheral_nervous_system.version import VERSION`. This will cause an `ImportError` on remote agents during self-updates, causing the agent to "die" without restarting.
- When updating the agent, increment the version string in `agent_service.py` and ensure it matches the server's version in `peripheral_nervous_system/version.py`.

## 2. Dependencies
- Keep external dependencies to a minimum. 
- Stick to standard library modules plus `psutil`.

## 3. Self-Update Mechanism
- The `UPDATE_SELF` command writes the received content to its own file.
- It restarts using `subprocess.Popen` with `CREATE_NEW_CONSOLE | DETACHED_PROCESS` on Windows to ensure the child process outlives the parent.
- The parent process MUST exit using `os._exit(0)` immediately after spawning the child.

## 4. Path Discovery
- The agent should remain stateless. It should probe paths requested by the server rather than maintaining its own configuration.
