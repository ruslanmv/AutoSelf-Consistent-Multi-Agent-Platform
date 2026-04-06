#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run.py — unified launcher for backend (FastAPI) and frontend (Flask)

Non-destructive upgrade:
- Keeps original behavior and messages, adds optional CLI flags and health checks.
- Loads secrets from Colab user secrets or local .env (unchanged from original).
- Sets SERVER_URL for the frontend.
- Waits for backend /health before announcing readiness (with timeout & retries).
- Optional ngrok tunneling in Colab (default) and locally via --ngrok.
- Clean shutdown of tunnels on Ctrl+C.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import signal
import argparse
import atexit
import webbrowser
from typing import Optional

import uvicorn

try:
    import requests  # for health checks
except Exception:  # pragma: no cover
    requests = None

# --- Environment-Aware Configuration ---

# 1) Detect Google Colab
IN_COLAB = 'google.colab' in sys.modules


def _load_environment() -> None:
    """Load secrets from Colab or .env. Non-fatal if .env missing locally."""
    if IN_COLAB:
        print("🚀 Running in Google Colab environment.")
        try:
            from google.colab import userdata  # type: ignore
            secrets_map = {
                'WATSONX_API_KEY': 'WATSONX_API_KEY',
                'PROJECT_ID': 'PROJECT_ID',
                'WATSONX_URL': 'WATSONX_URL',
                'NGROK_AUTHTOKEN': 'NGROK_AUTHTOKEN',
            }
            for key, secret_name in secrets_map.items():
                value = userdata.get(secret_name)
                if value:
                    os.environ[key] = value
                    print(f"✅ Loaded secret '{secret_name}' into environment variable '{key}'.")
                else:
                    # Non-fatal for Watsonx; fatal for NGROK only if tunneling requested later
                    print(f"⚠️ Colab secret '{secret_name}' not found.")
        except Exception as e:
            print(f"⚠️ Error loading Colab secrets: {e}")
            # Do not exit; allow offline mode.
    else:
        print("🏡 Running in a local environment.")
        try:
            from dotenv import load_dotenv  # type: ignore
            if load_dotenv():
                print("✅ .env file found and loaded.")
            else:
                print("⚠️ .env file not found. Proceeding with current environment.")
        except Exception:
            print("⚠️ 'python-dotenv' not installed. Cannot load .env file.")


# --- Server and Client Functions ---

def run_fastapi_server(port: int) -> None:
    """Run the Uvicorn server in a background thread."""
    # Import after env is loaded
    from server import app as fastapi_app  # type: ignore
    print(f"🔥 Starting FastAPI backend server on http://localhost:{port}")
    uvicorn.run(fastapi_app, host="0.0.0.0", port=port, log_level="warning")


def run_flask_client(port: int) -> None:
    """Run the Flask client in a background thread."""
    from client import app as flask_app  # type: ignore
    print(f"🎨 Starting Flask frontend server on http://localhost:{port}")
    flask_app.run(host="0.0.0.0", port=port, debug=False)


# --- Health checks ---

def wait_for_backend_health(base_url: str, timeout_s: int = 30) -> bool:
    """Poll /health on the backend until success or timeout. Returns True if healthy."""
    if requests is None:
        # If requests is not available, skip health check
        print("⚠️ 'requests' not available; skipping backend health check.")
        return True

    health_url = base_url.rstrip('/') + "/health"
    deadline = time.time() + max(1, timeout_s)
    last_err: Optional[str] = None
    while time.time() < deadline:
        try:
            r = requests.get(health_url, timeout=2.5)
            if r.status_code == 200:
                return True
            last_err = f"HTTP {r.status_code}"
        except Exception as e:  # ConnectionError/Timeout
            last_err = str(e)
        time.sleep(0.5)
    print(f"❌ Backend health check failed at {health_url}: {last_err}")
    return False


# --- ngrok helpers ---

_ngrok_active_tunnels: list[str] = []


def start_ngrok_tunnel(port: int, name: str, bind_tls: bool = False) -> Optional[str]:
    """Start an ngrok tunnel for a local port and return the public URL, or None on failure."""
    try:
        from pyngrok import ngrok, conf  # type: ignore
    except Exception as e:
        print(f"⚠️ ngrok unavailable: {e}")
        return None

    token = os.environ.get("NGROK_AUTHTOKEN")
    if token:
        conf.get_default().auth_token = token
    else:
        print("⚠️ NGROK_AUTHTOKEN not set; attempting anonymous tunnel (limits may apply).")

    try:
        t = ngrok.connect(addr=port, name=name, proto="http", bind_tls=bind_tls)
        public_url = t.public_url
        _ngrok_active_tunnels.append(public_url)
        return public_url
    except Exception as e:
        print(f"❌ Failed to start ngrok tunnel for {name} on port {port}: {e}")
        return None


def stop_all_ngrok() -> None:
    try:
        from pyngrok import ngrok  # type: ignore
    except Exception:
        return
    for url in list(_ngrok_active_tunnels):
        try:
            ngrok.disconnect(url)
        except Exception:
            pass
        finally:
            _ngrok_active_tunnels.remove(url)
    try:
        ngrok.kill()
    except Exception:
        pass


# --- CLI ---

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Launch AutoSelf backend (FastAPI) and frontend (Flask)")
    p.add_argument("--server-port", type=int, default=int(os.environ.get("AUTOSELF_BACKEND_PORT", 8008)),
                   help="Port for FastAPI backend (default: 8008)")
    p.add_argument("--client-port", type=int, default=int(os.environ.get("AUTOSELF_FRONTEND_PORT", 5000)),
                   help="Port for Flask frontend (default: 5000)")
    p.add_argument("--no-browser", action="store_true", help="Do not open the dashboard in a web browser")
    p.add_argument("--ngrok", action="store_true", help="Start ngrok tunnels locally (Colab tunnels start by default)")
    p.add_argument("--health-timeout", type=int, default=30, help="Seconds to wait for /health readiness")
    return p.parse_args()


# --- Main ---

def main() -> int:
    _load_environment()
    print("-" * 50)
    args = parse_args()

    SERVER_PORT = int(args.server_port)
    CLIENT_PORT = int(args.client_port)

    # Start servers in background threads (daemon so they exit with main)
    backend_thread = threading.Thread(target=run_fastapi_server, args=(SERVER_PORT,), daemon=True)
    frontend_thread = threading.Thread(target=run_flask_client, args=(CLIENT_PORT,), daemon=True)
    backend_thread.start()
    frontend_thread.start()

    # Compute local URLs
    local_backend_url = f"http://localhost:{SERVER_PORT}"
    local_dashboard_url = f"http://localhost:{CLIENT_PORT}"

    # Wait a moment before health probe
    print("Waiting for servers to start...")
    time.sleep(1.0)

    # Health check backend (best-effort)
    healthy = wait_for_backend_health(local_backend_url, timeout_s=int(args.health_timeout))
    if not healthy:
        print("⚠️ Proceeding despite failed health check (the server may still be starting).")

    # Establish URLs (local or ngrok)
    backend_url = local_backend_url
    dashboard_url = local_dashboard_url

    # In Colab, start tunnels by default; locally, only if --ngrok is passed
    use_ngrok = IN_COLAB or bool(args.ngrok)
    if use_ngrok:
        print("Starting ngrok tunnels...")
        # Backend tunnel (TLS on for backend by default)
        be_pub = start_ngrok_tunnel(SERVER_PORT, name="backend-server", bind_tls=True)
        if be_pub:
            backend_url = be_pub
        # Frontend tunnel
        fe_pub = start_ngrok_tunnel(CLIENT_PORT, name="frontend-dashboard", bind_tls=False)
        if fe_pub:
            dashboard_url = fe_pub

    # Set SERVER_URL for the frontend to call the backend
    os.environ['SERVER_URL'] = backend_url

    # Register cleanup
    def _cleanup():
        stop_all_ngrok()
        print("Cleanup complete.")
    atexit.register(_cleanup)

    def _sigint_handler(signum, frame):  # type: ignore[unused-argument]
        print("\nShutting down...")
        sys.exit(0)
    try:
        signal.signal(signal.SIGINT, _sigint_handler)
        signal.signal(signal.SIGTERM, _sigint_handler)
    except Exception:
        pass

    # Announce readiness
    print("\n" + "=" * 55)
    if IN_COLAB or use_ngrok:
        print("🚀 FRAMEWORK IS READY AND ACCESSIBLE PUBLICLY! 🚀")
    else:
        print("🚀 FRAMEWORK IS READY LOCALLY! 🚀")
    print(f"Backend API: {backend_url}")
    print(f"👉 Dashboard: {dashboard_url}")
    print("=" * 55 + "\n")

    # Open browser locally unless suppressed
    if not IN_COLAB and not args.no_browser:
        try:
            webbrowser.open(dashboard_url)
            print("Opened dashboard in your default web browser.")
        except Exception:
            print("Could not automatically open browser. Please navigate to the URL manually.")

    # Keep the main thread alive while background threads serve
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        stop_all_ngrok()
        print("Execution finished.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
