import os, time
from pathlib import Path
from config import SUPPORTED_FORMATS, MAX_UPLOAD_SIZE_MB, MIME_TYPES, CRITICAL_FIELDS
from generator import client, call_gemini
from google.genai import types
from model import InvoiceData, ExtractedInvoice

MAGIC_BYTES = {
    b'%PDF': 'application/pdf',
    b'\xff\xd8\xff': 'image/jpeg',      # JPEG SOI marker
    b'\x89PNG': 'image/png',            # PNG signature
    b'RIFF': 'image/webp',              # WEBP container (needs deeper check, but okay)
}
def validate_magic_bytes(file_path: str):
    with open(file_path, 'rb') as f:
        header = f.read(12)

    # WEBP: RIFF container with "WEBP" at bytes 8-11 — a plain RIFF
    # prefix alone (e.g. .wav, .avi) is not enough to qualify.
    if header.startswith(b'RIFF') and header[8:12] == b'WEBP':
        return True

    for sig, mime in MAGIC_BYTES.items():
        if header.startswith(sig):
            return True

    raise ValueError(f"File content does not match a supported format (magic bytes: {header.hex()})")

def validate_file(file_path: str):
    file = Path(file_path)
    # 1. Extension check
    if file.suffix.lower() not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported file type: {file.suffix}")

    # 2. Magic bytes check (content-based)
    validate_magic_bytes(file_path)

    # 3. Size check
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if file_size_mb > MAX_UPLOAD_SIZE_MB:
        raise ValueError(f"File too large: {file_size_mb:.1f}MB")

    return file_size_mb

def prepare_for_gemini(file_path: str):
    file = Path(file_path)
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    mime_type = MIME_TYPES[file.suffix.lower()]
    uploaded_file = None
    if file.suffix.lower() == ".pdf" or file_size_mb > 4:
        # Upload to File API
        uploaded_file = client.files.upload(file=file_path)

        # Wait for processing (Gemini needs time to make the file ready)
        timeout = 30  # seconds
        start = time.time()
        while uploaded_file.state.name == "PROCESSING":
            if time.time() - start > timeout:
                raise TimeoutError(f"File processing timeout: {file.name}")
            time.sleep(2)
            uploaded_file = client.files.get(name=uploaded_file.name)

        if uploaded_file.state.name == "FAILED":
            raise ValueError(f"File processing failed: {file.name}")

        content = types.Part(
            file_data=types.FileData(
                mime_type=mime_type,
                file_uri=uploaded_file.uri
            )
        )
    else:
        content = types.Part(
            inline_data=types.Blob(
                mime_type=mime_type,
                data=file.read_bytes()
            )
        )
    return content, uploaded_file

def calculate_confidence(invoice: InvoiceData) -> float:
    filled = sum(1 for field in CRITICAL_FIELDS if getattr(invoice, field) is not None)
    completeness = filled / len(CRITICAL_FIELDS)

    if all(v is not None for v in (invoice.subtotal, invoice.tax_total, invoice.total_amount_due)):
        expected = invoice.subtotal + invoice.tax_total
        if abs(expected - invoice.total_amount_due) > 0.05:
            return min(completeness, 0.5)

    return completeness

def extract_invoice(file_path: str) -> InvoiceData:
    validate_file(file_path)
    content, uploaded_file = prepare_for_gemini(file_path)

    # Text prompt to guide Gemini
    text_part = types.Part(text="""
You are an invoice extraction expert.

Extract the following fields from this invoice document:
- vendor_name (company name of the seller)
- vendor_tax_id (tax identification number, if present)
- vendor_address (full address)
- client_name (buyer/customer name)
- invoice_number
- invoice_date (YYYY-MM-DD format)
- due_date (if present)
- currency (three-letter code, e.g., USD, EUR, GBP)
- subtotal (net amount before tax)
- tax_total (total tax amount)
- total_amount_due (final amount to pay)
- iban (bank account number, if present)
- notes (any special terms or remarks)

For line items, extract each product/service as an object with:
- item_number (optional)
- item_description
- qty (quantity, as number)
- unit_price (price per unit)
- tax_rate (as decimal, e.g., 0.1 for 10%)
- tax_amount
- line_total

Confidence scoring is handled separately. Return null for any missing field.
Do not hallucinate. If a section is illegible, leave it null.
""")

    try:
        extracted = call_gemini([text_part, content], ExtractedInvoice)
        invoice = InvoiceData(
            filename=Path(file_path).name,
            confidence=0.0,  # placeholder, computed below
            **extracted.model_dump(by_alias=False)
        )
        invoice.confidence = calculate_confidence(invoice)
        return invoice
    finally:
        if uploaded_file is not None:
            client.files.delete(name=uploaded_file.name)