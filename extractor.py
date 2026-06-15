"""handles one invoice file START 2 FINISH
1. Validate the file (right extension? not too big?)
2. Prepare the file for Gemini (small image → inline, big or PDF → File API)
3. Call generator.call_gemini() → get back an InvoiceData object
4. Fill in filename and confidence, return the completed object
"""
import os
from config import SUPPORTED_FORMATS, MAX_UPLOAD_SIZE_MB, MIME_TYPES
from pathlib import Path
from generator import client, call_gemini
from google.genai import types
from config import CRITICAL_FIELDS

def validate_file(file_path: str ):
    file = Path(file_path) # <- convert string to Path, now .suffix works

    #Extension Check
    if file.suffix.lower() not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported file type: {file.suffix}")

    #File Size Check
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if file_size_mb > MAX_UPLOAD_SIZE_MB:
        raise ValueError(f"File too large: {file_size_mb:.1f}MB")

    return file_size_mb

def prepare_for_gemini(file_path: str):
    file = Path(file_path)
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    mime_type = MIME_TYPES[file.suffix.lower()]

    uploaded_file = None  # sentinel
    try:
        # File API (Big files / PDFs)
        if file.suffix.lower() == ".pdf" or file_size_mb > 4:
            uploaded_file = client.files.upload(path=file_path)

            content =  types.Part(
                file_data=types.FileData(
                    mime_type=mime_type,
                    file_uri=uploaded_file.uri
                )
            )
            return content
         # iNLINE Mode (small images)
        else:
            content = types.Part(
                inline_data=types.Blob(
                    mime_type=mime_type,
                    data=file.read_bytes()
                )
            )
            return content

        #gemini call :
        invoice = call_gemini(content)

    finally:
        if uploaded_file is not None:
            client.files.delete(name=uploaded_file.name)

from model import InvoiceData


def calculate_confidence(invoice: InvoiceData) -> float:
    # Check 1: how many critical fields are filled in
    filled = sum(1 for field in CRITICAL_FIELDS if getattr(invoice, field) is not None)
    completeness = filled / len(CRITICAL_FIELDS)

    # Check 2: does the math add up?
    if all([invoice.subtotal, invoice.tax_total, invoice.total_amount_due]):
        expected = invoice.subtotal + invoice.tax_total
        if abs(expected - invoice.total_amount_due) > 0.05:
            return min(completeness, 0.5)  # math is wrong → cap at 0.5 no matter what

    return completeness

def extract_invoice(file_path:str) -> InvoiceData:
    validate_file(file_path)
    content = prepare_for_gemini(file_path)
    invoice = call_gemini([content], InvoiceData)
    invoice.filename = Path(file_path).name
    invoice.confidence = calculate_confidence(invoice)
    return invoice