GEMINI_MODEL_NAME = "gemini-2.5-flash"
CONFIDENCE_THRESHOLD = 0.75
SUPPORTED_FORMATS = [".pdf", ".jpg", ".png", ".jpeg", ".webp"]
MAX_UPLOAD_SIZE_MB= 10
MAX_WORKERS = 1
TIMEOUT= 30
MAX_RETRIES = 6
MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf"
}
CRITICAL_FIELDS = ["vendor_name", "invoice_date", "invoice_number","total_amount_due", "currency"]