import sys
import os

# Add root directory to sys.path so app and utils can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, init_db, seed_data

# Ensure database tables and initial seed data are populated on serverless startup
try:
    init_db()
    seed_data()
except Exception as e:
    print(f"Vercel serverless startup DB note: {e}")
