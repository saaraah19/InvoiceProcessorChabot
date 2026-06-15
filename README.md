# Invoice Processor

![Invoice Processor UI](./screenshot.png)
[![Live Demo](https://img.shields.io/badge/demo-live-brightgreen)](https://your-app.railway.app)

> ⚠️ Replace the screenshot, demo link, and GitHub username placeholders below before publishing.

AI-powered invoice data extraction and accounting export tool. Upload one invoice or a batch — the system extracts structured data using Gemini Vision, scores each extraction by confidence, and delivers ready-to-use CSV/Excel exports in seconds.

Built as a portfolio MVP demonstrating an end-to-end document-processing pipeline: file validation, async batch processing with progress tracking, structured LLM extraction, and multi-format export.

---

## What it does

- Extracts structured data from invoices in PDF, JPG, PNG, or WEBP format
- Pulls vendor name, invoice number, date, line items, subtotal, tax, total, IBAN, currency, and notes
- Classifies each invoice into an accounting category (Software & Subscriptions, Travel, Professional Services, Utilities, Meals & Entertainment, Office Supplies, Other)
- Scores every extraction with a confidence value (0.0–1.0) computed in code from two signals: field completeness and arithmetic consistency (subtotal + tax ≈ total)
- Handles batch processing with live progress (X of Y files), backed by a SQLite job store
- Deduplicates files within a batch by MD5 hash — identical files are processed only once
- Exports results as a detailed CSV (one row per line item), a summary CSV (one row per invoice), or a 3-sheet Excel workbook split by confidence

---

## Exports — what each one contains

| Export | Endpoint | Granularity | Notes |
|---|---|---|---|
| Detailed CSV | `/export/{job_id}` | One row per line item | All extracted invoices, regardless of confidence. Includes a separate `_errors.csv` if any extraction errors occurred. |
| Summary CSV | `/export/summary/{job_id}` | One row per invoice | Drops invoices with no `invoice_number`, `vendor_name`, or `total_amount_due` (treated as non-invoices). No line items. |
| Excel workbook | `/export/excel/{job_id}` | One row per invoice, 3 sheets | **Approuvé**: confidence ≥ `CONFIDENCE_THRESHOLD` (0.75). **À revoir**: below threshold. **Erreurs**: pipeline failures + invoices with no usable data. |

Only the Excel export tiers invoices by confidence — the CSV exports are flat dumps of everything that came back from the pipeline.

---

## Data flow

```
User uploads file(s) via browser UI
        │
        ▼
FastAPI receives upload (main.py)
        │
        ├─── Single file ──► POST /process
        │                         │
        │                         ▼
        │                   extractor.py
        │                   ┌─────────────────────────────┐
        │                   │ 1. Validate: extension,      │
        │                   │    magic bytes, size (≤10MB) │
        │                   │ 2. Route by size + type:      │
        │                   │    images ≤4MB → inline_data  │
        │                   │    PDF / >4MB  → File API      │
        │                   │ 3. Call Gemini Vision           │
        │                   │    (generator.py: retries on    │
        │                   │     429/503, 6 attempts,         │
        │                   │     exponential backoff)         │
        │                   │ 4. Score confidence              │
        │                   │    - field completeness          │
        │                   │    - arithmetic check             │
        │                   └─────────────────────────────┘
        │                         │
        │                         ▼
        │                   InvoiceData (Pydantic) → JSON response
        │
        └─── Batch files ──► POST /batch
                                  │
                                  ▼
                            job_id created (jobs.py → SQLite)
                            returned to UI immediately
                                  │
                                  ▼
                            processor.py (background task)
                            ┌─────────────────────────────┐
                            │ 1. Discover supported files   │
                            │ 2. MD5 dedup — skip dupes      │
                            │ 3. ThreadPoolExecutor           │
                            │    (MAX_WORKERS, default 1)     │
                            │ 4. extract_invoice() per file    │
                            │ 5. Collect via as_completed()    │
                            │ 6. Route: success → results,     │
                            │    failure → errors              │
                            │ 7. Save results + errors to DB    │
                            │ 8. Update job status: done         │
                            │ 9. Clean up uploaded batch files    │
                            └─────────────────────────────┘
                                  │
                            UI polls GET /progress/{job_id}
                            every second
                                  │
                                  ▼ status = done
                            GET /results/{job_id}
                            → results + errors shown in table
                                  │
                                  ▼
                            User downloads CSV / Excel export
```

---

## Project structure

```
invoice-processor/
├── config.py          # Constants: model names, thresholds, formats, batch settings
├── model.py            # Pydantic schemas: InvoiceData + nested Item
├── generator.py        # Gemini client + call_gemini() with retry logic
├── extractor.py         # Single-invoice pipeline: validate → prepare → extract → score
├── jobs.py               # SQLite job store: create, update, save, retrieve
├── processor.py           # Batch orchestration: dedup, ThreadPoolExecutor, cleanup
├── convertor.py            # InvoiceData list → CSV exports
├── main.py                  # FastAPI app: endpoints + static file serving
├── static/
│   └── index.html             # Upload UI: drag & drop, progress polling, results table
├── .env                          # API keys (never committed)
├── .env.example                   # Template for required env vars
├── .gitignore
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## API endpoints

| Endpoint | Method | Input | Output |
|---|---|---|---|
| `/` | GET | — | Upload UI (`static/index.html`) |
| `/health` | GET | — | `{ status, model }` — used for container health checks |
| `/process` | POST | Single file (multipart) | `InvoiceData` as JSON |
| `/batch` | POST | Multiple files (multipart) | `{ job_id, message }` |
| `/status/{job_id}` | GET | job_id | `{ job_id, status }` |
| `/progress/{job_id}` | GET | job_id | `{ job_id, status, total, processed }` |
| `/results/{job_id}` | GET | job_id | `{ job_id, results, errors }` |
| `/export/{job_id}` | GET | job_id | Detailed CSV download |
| `/export/summary/{job_id}` | GET | job_id | Summary CSV download |
| `/export/excel/{job_id}` | GET | job_id | 3-sheet Excel download |

Rate limits: `10/minute` on `/process`, `5/minute` on `/batch`, keyed by client IP (via `slowapi`, with Railway's proxy headers respected).

---

## Confidence scoring

Every extracted invoice gets a confidence score between 0.0 and 1.0, computed in code — not self-reported by the AI.

**Signal 1 — Field completeness:**
Checks how many critical fields came back non-null.
Critical fields: `vendor_name`, `invoice_date`, `invoice_number`, `total_amount_due`, `currency`.
Score = filled critical fields ÷ total critical fields.

**Signal 2 — Arithmetic consistency:**
If `subtotal`, `tax_total`, and `total_amount_due` are all present, checks `abs((subtotal + tax_total) - total_amount_due) ≤ 0.05`.
If the math fails, confidence is capped at 0.5 regardless of completeness — a plausible-looking wrong number is more dangerous than a missing field.

The threshold used to split "Approuvé" vs "À revoir" in the Excel export is `CONFIDENCE_THRESHOLD = 0.75` in `config.py`.

---

## Gemini Vision integration

Two routing strategies depending on file characteristics:

**Inline data** — images ≤ 4MB:
```
file bytes → types.Blob → types.Part(inline_data=...)
```

**File API** — PDFs and files > 4MB:
```
upload to Gemini File API → poll every 2s (30s timeout) until ready
→ types.Part(file_data=...) → always deleted in finally block
```

Retry logic on every Gemini call (`generator.py`):
- Triggers on `429 RESOURCE_EXHAUSTED` or `503 UNAVAILABLE`
- Up to `MAX_RETRIES = 6` attempts
- Exponential backoff: 5s, 10s, 20s, 40s, 60s, 60s
- Raises `RuntimeError` if all attempts fail

---

## Tech stack

| Layer | Technology |
|---|---|
| AI extraction | Google Gemini 2.5 Flash (Vision) |
| Schema validation | Pydantic v2 |
| API framework | FastAPI |
| Concurrency | `ThreadPoolExecutor`, `MAX_WORKERS` (default 1, configurable in `config.py`) |
| Job tracking | SQLite (WAL mode) |
| Spreadsheet export | openpyxl |
| Containerization | Docker + Docker Compose |
| Deployment | Railway |
| Frontend | Vanilla HTML/CSS/JS (no framework) |

`MAX_WORKERS` defaults to 1 to stay comfortably under Gemini's free-tier rate limit (15 requests/minute). Increase it if you have a paid Gemini quota — just be aware that higher concurrency increases the chance of SQLite write contention on `jobs.db` (mitigated, but not eliminated, by WAL mode).

---

## Run locally

**1. Clone and set up environment:**
```bash
git clone https://github.com/yourusername/invoice-processor
cd invoice-processor
```

**2. Add your API key:**
```bash
cp .env.example .env
# then edit .env and set GEMINI_API_KEY=your_key_here
```

**3. Run with Docker:**
```bash
docker compose up --build
```

**4. Open the UI:**
```
http://localhost:8000
```

---

## Run without Docker

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

---

## Environment variables

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio API key. The app fails fast at startup if this is missing. |

Get a free key at: https://aistudio.google.com

---

## Deployment (Railway)

1. Push repo to GitHub
2. Go to railway.app → New Project → Deploy from GitHub
3. Select this repo
4. Add `GEMINI_API_KEY` under Variables
5. Set the healthcheck path to `/health` in service settings
6. Railway detects the Dockerfile and deploys automatically
7. Public URL is generated — share it directly with clients

`docker-compose.yml` is for local development only — Railway builds and runs the `Dockerfile` directly and does not use Compose volumes.

---

## Limitations

- Handwritten invoices may score lower confidence — recommend a clear photo in good lighting
- Vector graphics inside PDFs (charts drawn as shapes) are not extracted as images
- Free Gemini tier: 15 requests/minute. Large batches with `MAX_WORKERS = 1` will queue accordingly — a 30-invoice batch can take several minutes
- Storage is ephemeral: `jobs.db`, `uploads/`, and `outputs/` live on the container filesystem and are not persisted across deploys/restarts. Uploaded files for a batch are deleted automatically once that batch finishes processing
- No authentication — anyone with the URL can use the app (acceptable for a portfolio demo, not for production multi-tenant use)

---

## Use cases and pricing reference

| Deliverable | Scope | Price range |
|---|---|---|
| Single-client invoice processor | Setup + deployment | $400–600 |
| Custom category taxonomy | Add client's chart of accounts | $100–150 |
| Accounting software CSV format | Match QuickBooks/Xero column layout | $75–100 |
| Monthly maintenance retainer | Prompt tuning + monitoring | $75–150/month |