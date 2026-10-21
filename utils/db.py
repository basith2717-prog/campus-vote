import sqlite3
import os
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Serverless platforms (like Vercel) have a read-only filesystem except /tmp
if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME") or not os.access(BASE_DIR, os.W_OK):
    DB_PATH = "/tmp/voting.db"
    local_db = os.path.join(BASE_DIR, "database", "voting.db")
    if os.path.exists(local_db) and not os.path.exists(DB_PATH):
        try:
            shutil.copy2(local_db, DB_PATH)
        except Exception:
            pass
else:
    DB_PATH = os.path.join(BASE_DIR, "database", "voting.db")

def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)
