#!/usr/bin/env python3
"""
Unified Process Manager & Startup Controller for ProjectPulse AI
Ensures:
1. Exactly ONE backend server instance runs at a time.
2. Stale or previous processes on the configured port are safely detected and stopped.
3. No duplicate processes (Werkzeug reloader disabled by default).
4. Clean, isolated, non-overlapping console logs.
5. Preserves existing application data without overwriting.
"""

import atexit
import logging
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / 'instance'
PID_FILE = INSTANCE_DIR / 'server.pid'

# Configure logging to provide clean, separated output
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
    stream=sys.stdout
)
logger = logging.getLogger('projectpulse')


def is_port_in_use(host: str, port: int) -> bool:
    """Check whether a TCP port is currently occupied."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        result = sock.connect_ex((host, port))
        return result == 0


def find_pids_on_port(port: int):
    """Find all process IDs listening on the specified port across platforms."""
    pids = set()
    if sys.platform == 'win32':
        try:
            output = subprocess.check_output(
                ['netstat', '-ano', '-p', 'tcp'],
                universal_newlines=True,
                stderr=subprocess.DEVNULL
            )
            for line in output.splitlines():
                line = line.strip()
                if f":{port} " in line and "LISTENING" in line:
                    parts = line.split()
                    if parts:
                        try:
                            pid = int(parts[-1])
                            if pid > 0 and pid != os.getpid():
                                pids.add(pid)
                        except (ValueError, IndexError):
                            pass
        except Exception as e:
            logger.debug(f"Could not scan netstat: {e}")
    else:
        try:
            output = subprocess.check_output(
                ['lsof', '-ti', f':{port}'],
                universal_newlines=True,
                stderr=subprocess.DEVNULL
            )
            for line in output.splitlines():
                try:
                    pid = int(line.strip())
                    if pid != os.getpid():
                        pids.add(pid)
                except ValueError:
                    pass
        except Exception:
            pass

    return list(pids)


def is_pid_alive(pid: int) -> bool:
    """Check whether a process with the given PID is currently running."""
    if pid <= 0:
        return False
    if sys.platform == 'win32':
        try:
            output = subprocess.check_output(
                ['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV', '/NH'],
                universal_newlines=True,
                stderr=subprocess.DEVNULL
            )
            return str(pid) in output
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


def terminate_pid(pid: int):
    """Terminate a specific process ID cleanly."""
    if pid <= 0 or pid == os.getpid():
        return
    logger.info(f"Terminating previous instance (PID: {pid})...")
    if sys.platform == 'win32':
        try:
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False
            )
        except Exception as e:
            logger.warning(f"Failed to kill PID {pid}: {e}")
    else:
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.5)
            if is_pid_alive(pid):
                os.kill(pid, signal.SIGKILL)
        except Exception as e:
            logger.warning(f"Failed to kill PID {pid}: {e}")


def cleanup_stale_instances(host: str, port: int):
    """Detect and stop any existing backend instances or port holders."""
    # Check PID file first
    INSTANCE_DIR.mkdir(exist_ok=True)
    if PID_FILE.exists():
        try:
            stale_pid = int(PID_FILE.read_text().strip())
            if is_pid_alive(stale_pid):
                logger.info(f"Found active lock file for PID {stale_pid}.")
                terminate_pid(stale_pid)
        except Exception:
            pass
        finally:
            if PID_FILE.exists():
                try:
                    PID_FILE.unlink()
                except Exception:
                    pass

    # Check port occupancy
    if is_port_in_use(host, port):
        logger.warning(f"Port {port} is occupied. Scanning for listening processes...")
        occupying_pids = find_pids_on_port(port)
        if occupying_pids:
            for pid in occupying_pids:
                terminate_pid(pid)
        else:
            logger.warning(f"Port {port} occupied but PID not directly identifiable. Waiting for release...")

        # Wait up to 5 seconds for the port to become available
        for _ in range(10):
            time.sleep(0.5)
            if not is_port_in_use(host, port):
                logger.info(f"Port {port} successfully freed.")
                break
        else:
            if is_port_in_use(host, port):
                logger.error(f"Port {port} could not be freed. Please verify manual port usage.")
                sys.exit(1)


def register_pid_file():
    """Write current PID to instance/server.pid and register clean shutdown cleanup."""
    INSTANCE_DIR.mkdir(exist_ok=True)
    current_pid = os.getpid()
    PID_FILE.write_text(str(current_pid))

    def remove_pid():
        try:
            if PID_FILE.exists() and PID_FILE.read_text().strip() == str(current_pid):
                PID_FILE.unlink()
        except Exception:
            pass

    atexit.register(remove_pid)

    def sig_handler(sig, frame):
        logger.info(f"Shutdown signal received ({sig}). Exiting cleanly...")
        remove_pid()
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, sig_handler)
        signal.signal(signal.SIGTERM, sig_handler)
    except Exception:
        pass


def print_banner(host: str, port: int, debug: bool):
    """Print a clean, single-session startup header."""
    url = f"http://{host}:{port}" if host != '0.0.0.0' else f"http://127.0.0.1:{port}"
    banner = f"""
======================================================================
  ProjectPulse AI - Intelligent Infrastructure Monitoring Platform
======================================================================
  * Process ID (PID)   : {os.getpid()}
  * Port & Host        : {host}:{port}
  * Access URL         : {url}
  * Mode               : {'Development (Debug on)' if debug else 'Production / Clean Runtime'}
  * Auto-Reloader      : DISABLED (Single Process Enforced)
  * Port Management    : VERIFIED CLEAN (No duplicate instances)
======================================================================
"""
    print(banner, flush=True)


def main():
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    port = int(os.environ.get('PORT') or os.environ.get('FLASK_PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() in ('true', '1')

    # Step 1: Detect and clean up any previous instance holding the port
    cleanup_stale_instances(host, port)

    # Step 2: Register single instance lock
    register_pid_file()

    # Step 3: Print clean session banner
    print_banner(host, port, debug)

    # Step 4: Load application safely
    try:
        from app import app
        from database import db
        from database.migration import ensure_database_schema
        from routes.auth import ensure_demo_users

        with app.app_context():
            logger.info("Verifying database schema and initial state...")
            ensure_database_schema()
            db.create_all()
            ensure_demo_users()
            logger.info("Database and demo credentials ready.")

    except Exception as e:
        logger.critical(f"FATAL: Application initialization failed: {e}", exc_info=True)
        sys.exit(1)

    # Step 5: Start server with Werkzeug reloader DISABLED
    # Disabling the reloader guarantees exactly ONE process and eliminates overlapping output.
    try:
        logger.info(f"Starting ProjectPulse AI backend server on {host}:{port}...")
        app.run(
            host=host,
            port=port,
            debug=debug,
            use_reloader=False,
            threaded=True
        )
    except (KeyboardInterrupt, SystemExit):
        logger.info("Backend server stopped cleanly.")
    except Exception as e:
        logger.critical(f"FATAL: Server crashed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
