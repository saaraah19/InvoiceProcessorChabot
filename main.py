import uuid
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
    # save all uploads to a job-specific folder
    batch_id = str(uuid.uuid4())
    batch_dir = UPLOAD_DIR / batch_id
    batch_dir.mkdir()

    for file in files:
        file_path = batch_dir / file.filename
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

    # start processing in background, return job_id immediately
    background_tasks.add_task(processor.run_batch, str(batch_dir))

    return {"job_id": batch_id, "message": "Batch started"}


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
        raise HTTPException(status_code=404, detail="Job not found")
    if row["status"] != "done":
        raise HTTPException(status_code=400, detail="Job not finished yet")

    results = json.loads(row["results"])
    errors = []  # errors stored separately in a real v2

    output_path = str(OUTPUT_DIR / f"{job_id}.csv")
    convertor.convert_to_csv(results, errors, output_path)

    return FileResponse(
        output_path,
        media_type="text/csv",
        filename=f"invoices_{job_id}.csv"
    )