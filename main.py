import uuid
import csv
import json
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import shutil
import jobs
import processor
import convertor
from jobs import init_db

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Invoice Processor")


@app.on_event("startup")
def startup():
    init_db()  # creates the SQLite table if it doesn't exist


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def root():
    return FileResponse("static/index.html")


# ─── SINGLE FILE ─────────────────────────────────────────────
@app.post("/process")
async def process_single(file: UploadFile = File(...)):
    # save upload to disk
    file_path = UPLOAD_DIR / file.filename
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        from extractor import extract_invoice
        invoice = extract_invoice(str(file_path))
        return invoice.model_dump()
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


# ─── BATCH ───────────────────────────────────────────────────
@app.post("/batch")
async def process_batch(
        background_tasks: BackgroundTasks,
        files: list[UploadFile] = File(...)
):
    # Create job record NOW with the ID you'll return to client
    job_id = str(uuid.uuid4())          # ← single source of truth
    jobs.create_job(job_id, total_files=len(files))   # <-- add total_files
    batch_dir = UPLOAD_DIR / job_id      # ← use job_id for folder (optional but consistent)
    batch_dir.mkdir()

    for file in files:
        file_path = batch_dir / file.filename
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

    # Pass the SAME job_id to the background task
    background_tasks.add_task(processor.run_batch, str(batch_dir), job_id)

    return {"job_id": job_id, "message": "Batch started"}

# ─── STATUS ──────────────────────────────────────────────────
@app.get("/status/{job_id}")
def get_status(job_id: str):
    row = jobs.get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job_id, "status": row["status"]}


# ─── EXPORT ──────────────────────────────────────────────────
@app.get("/export/{job_id}")
def export_csv(job_id: str):
    row = jobs.get_job(job_id)
    if not row:
        raise HTTPException(404, "Job not found")
    if row["status"] != "done":
        raise HTTPException(400, "Job not finished yet")

    results = json.loads(row["results"]) if row["results"] else []
    output_path = str(OUTPUT_DIR / f"{job_id}.csv")

    # Always generate CSV even if no results
    convertor.convert_to_csv(results, [], output_path)  # pass empty errors list

    if not Path(output_path).exists():
        # fallback: create a minimal CSV with headers only
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["filename", "vendor", "total", "category", "confidence"])
            writer.writeheader()

    return FileResponse(output_path, media_type="text/csv", filename=f"invoices_{job_id}.csv")


@app.get("/results/{job_id}")
def get_results(job_id: str):
    row = jobs.get_job(job_id)
    if not row:
        raise HTTPException(404, "Job not found")
    if row["status"] != "done":
        raise HTTPException(400, "Job not finished yet")

    results = json.loads(row["results"]) if row["results"] else []
    return {"job_id": job_id, "results": results}

@app.get("/progress/{job_id}")
def get_progress(job_id: str):
    row = jobs.get_job(job_id)
    if not row:
        raise HTTPException(404, "Job not found")
    return {
        "job_id": job_id,
        "status": row["status"],
        "total": row["total_files"],
        "processed": row["processed_files"]
    }