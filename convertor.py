import csv
import json
from config import CONFIDENCE_THRESHOLD

WRONG_FILE_FLOOR = 0.2  # below this = wrong file entirely, not just low confidence

def convert_to_csv(results: list, errors: list, output_path: str):
    approved = []
    review = []
    wrong = []

    for record in results:
        if record["confidence"] >= CONFIDENCE_THRESHOLD:
            approved.append(record)
        elif record["confidence"] >= WRONG_FILE_FLOOR:
            review.append(record)
        else:
            wrong.append(record)  # uploaded something that isn't an invoice

    _write_csv(approved, output_path)
    _write_csv(review, output_path.replace(".csv", "_review.csv"))
    _write_csv(wrong, output_path.replace(".csv", "_wrong.csv"))
    _write_errors(errors, output_path.replace(".csv", "_errors.csv"))


def _write_csv(records: list, path: str):
    if not records:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)


def _write_errors(errors: list, path: str):
    if not errors:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["filename", "error"])
        writer.writeheader()
        writer.writerows(errors)