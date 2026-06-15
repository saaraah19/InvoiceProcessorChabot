import os,time
from pathlib import Path
from config import SUPPORTED_FORMATS, MAX_UPLOAD_SIZE_MB, MIME_TYPES, CRITICAL_FIELDS
from generator import client, call_gemini
from google.genai import types
from model import InvoiceData   # <-- moved up

MAGIC_BYTES = {
    b'%PDF': 'application/pdf',
    b'\xff\xd8\xff': 'image/jpeg',      # JPEG SOI marker
    b'\x89PNG': 'image/png',            # PNG signature
    b'RIFF': 'image/webp',              # WEBP container (needs deeper check, but okay)
}
def validate_magic_bytes(file_path: str):
    with open(file_path, 'rb') as f:
        header = f.read(4)
    # Check against known magic signatures
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
        uploaded_file = client.files.upload(path=file_path)

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
    if all([invoice.subtotal, invoice.tax_total, invoice.total_amount_due]):
        expected = invoice.subtotal + invoice.tax_total
        if abs(expected - invoice.total_amount_due) > 0.05:
            return min(completeness, 0.5)
    return completeness


# Only ONE extract_invoice – the correct one
def extract_invoice(file_path: str) -> InvoiceData:
    validate_file(file_path)
    content, uploaded_file = prepare_for_gemini(file_path)
    try:
        invoice = call_gemini([content], InvoiceData)
        invoice.filename = Path(file_path).name
        invoice.confidence = calculate_confidence(invoice)
        return invoice
    finally:
        if uploaded_file is not None:
            client.files.delete(name=uploaded_file.name)