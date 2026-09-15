"""
Entry point for the News Application
"""

import uvicorn
import subprocess
import os
import sys

def start_frontend():
    frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
    if os.path.exists(frontend_dir):
        print("[startup] Starting React Frontend...")
        # Use shell=True for npm on Windows
        return subprocess.Popen(
            "npm run dev", 
            cwd=frontend_dir, 
            shell=True,
            stdout=sys.stdout,
            stderr=sys.stderr
        )
    return None

if __name__ == "__main__":
    frontend_process = start_frontend()
    try:
        uvicorn.run(
            "backend.main:app",
            host="0.0.0.0",
            port=8002,
            reload=False,
            log_level="info",
        )
    finally:
        if frontend_process:
            print("\n[shutdown] Terminating React Frontend...")
            frontend_process.terminate()
