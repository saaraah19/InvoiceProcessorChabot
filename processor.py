import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from config import SUPPORTED_FORMATS, MAX_WORKERS
from extractor import extract_invoice
import jobs

def _get_md5(file_path: str) -> str:
    # unique fingerprint of the file's contents
    return hashlib.md5(Path(file_path).read_bytes()).hexdigest()

def _discover_files(folder_path: str) -> list:
    # find all supported files in the folder
    folder = Path(folder_path)
    return [
        str(f) for f in folder.rglob("*")
        if f.suffix.lower() in SUPPORTED_FORMATS
    ]

def run_batch(folder_path: str) -> str:
    # create a unique job id for this batch
    job_id = str(uuid.uuid4())
    jobs.create_job(job_id)

    files = _discover_files(folder_path)

    seen_hashes = set()  # MD5 dedup tracker
    results = []
    errors = []

    try:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # submit one task per file
            future_to_file = {}
            for file_path in files:
                # skip duplicates
                md5 = _get_md5(file_path)
                if md5 in seen_hashes:
                    continue
                seen_hashes.add(md5)
                future_to_file[executor.submit(extract_invoice, file_path)] = file_path

            # collect results as they finish
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    invoice = future.result()
                    results.append(invoice.model_dump())
                except Exception as e:
                    errors.append({
                        "filename": Path(file_path).name,
                        "error": str(e)
                    })

        jobs.save_results(job_id, results)
        jobs.update_status(job_id, "done")

    except Exception as e:
        jobs.update_status(job_id, "failed")
        raise

    return job_id