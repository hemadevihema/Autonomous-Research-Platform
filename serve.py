"""
Local Web Dashboard Server
==========================
Launches the FastAPI application using Uvicorn.
Run this script to access the web UI at http://localhost:8000.
"""
import sys
import webbrowser
import uvicorn
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))


def main():
    print("=" * 70)
    print("  AUTONOMOUS HEALTHCARE RESEARCH PLATFORM - WEB DASHBOARD")
    print("  Access the UI at: http://localhost:8000")
    print("=" * 70)
    
    # Try opening browser automatically
    try:
        webbrowser.open("http://localhost:8000")
    except Exception:
        pass

    uvicorn.run("api.index:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
