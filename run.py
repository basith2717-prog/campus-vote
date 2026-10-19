"""
VoteEase - College Digital Voting System Startup Script
Usage:
    python run.py
"""
import sys

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app import app, init_db, seed_data

if __name__ == "__main__":
    init_db()
    seed_data()
    print("\n" + "=" * 60)
    print(" VoteEase -- College Online Voting System")
    print("=" * 60)
    print(" Live URL:     http://127.0.0.1:5000")
    print(" Admin Portal: http://127.0.0.1:5000/admin (Key: admin123)")
    print(" Demo Student: STUDENT01 (Password: vote123)")
    print(" Public Tally: http://127.0.0.1:5000/results")
    print("=" * 60 + "\n")
    app.run(host="127.0.0.1", port=5000, debug=True)
