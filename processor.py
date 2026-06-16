import hashlib
import uuid
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from config import SUPPORTED_FORMATS, MAX_WORKERS
from extractor import extract_invoice
import jobs
import time
import shutil

logger = logging.getLogger(__name__)

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

def run_batch(folder_path: str, job_id: str) -> None:
    files = _discover_files(folder_path)
    logger.info(f"Batch {job_id}: {len(files)} files discovered")
    seen_hashes = set()
    results = []
    errors = []

    try:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_file = {}
            for file_path in files:
                md5 = _get_md5(file_path)
                if md5 in seen_hashes:
                    logger.info(f"Batch {job_id}: skipping duplicate file {Path(file_path).name}")
                    continue
                seen_hashes.add(md5)
                future_to_file[executor.submit(extract_invoice, file_path)] = file_path

            for future in as_completed(future_to_file):
                time.sleep(1)
                file_path = future_to_file[future]
                try:
                    invoice = future.result()
                    results.append(invoice.model_dump())
                except Exception as e:
                    logger.warning(f"Batch {job_id}: failed to process {Path(file_path).name}: {e}")
                    errors.append({
                        "filename": Path(file_path).name,
                        "error": str(e)
                    })
                jobs.increment_processed(job_id)

        jobs.save_errors(job_id, errors)
        jobs.save_results(job_id, results)
        jobs.update_status(job_id, "done")
        logger.info(f"Batch {job_id}: done — {len(results)} succeeded, {len(errors)} failed")

    except Exception as e:
        logger.error(f"Batch {job_id}: failed entirely: {e}")
        jobs.update_status(job_id, "failed")
        raise
    finally:
        shutil.rmtree(folder_path, ignore_errors=True)