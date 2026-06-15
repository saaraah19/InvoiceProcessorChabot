"""Its job is to remember whats happening with each batch so the frontend can show progress, thats it
It sores 3 things per job : job_id - a uniquee ID generatyed when the batch starts
status - "processing" / "done" / "failed"
results - the extracted invoice data as JSON, once done
4 functions : create_ob(joob_id), update_status(job_id, status), save_results(job_id, results), get_job(job_id)
"""

import sqlite3
import json

DB_PATH = "jobs.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # access columns by name
    return conn

def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT,
                results TEXT,
                total_files INTEGER DEFAULT 0,
                processed_files INTEGER DEFAULT 0
            )
        """)
        conn.commit()

def create_job(job_id: str, total_files: int = 0):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO jobs (job_id, status, results, total_files, processed_files) VALUES (?, ?, ?, ?, ?)",
            (job_id, "processing", None, total_files, 0)
        )
        conn.commit()

def update_status(job_id: str, status: str):
    with get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET status = ? WHERE job_id = ?",
            (status, job_id)
        )
        conn.commit()

def save_results(job_id: str, results: list):
    # results is already a list of dicts (from .model_dump())
    results_json = json.dumps(results)
    with get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET results = ? WHERE job_id = ?",
            (results_json, job_id)
        )
        conn.commit()

def get_job(job_id: str):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?",
            (job_id,)
        ).fetchone()
    return row

def increment_processed(job_id: str):
    with get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET processed_files = processed_files + 1 WHERE job_id = ?",
            (job_id,)
        )
        conn.commit()