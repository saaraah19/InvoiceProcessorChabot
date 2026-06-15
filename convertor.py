import csv
from typing import List, Dict, Any

WRONG_FILE_FLOOR = 0.2  # below this = wrong file entirely, not just low confidence


def flatten_invoice(invoice: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Convert a single invoice dictionary into a list of rows, one per line item.

    If the invoice has no items, we still produce a single row with empty item fields.
    This ensures the invoice is not lost in the export.

    Args:
        invoice: A dictionary representing an extracted invoice (from Gemini).

    Returns:
        List of row dictionaries, each containing invoice-level fields plus item details.
    """
    # Extract the items list; default to empty list if missing
    items = invoice.get("items", [])

    # If there are no items, create a dummy empty item so we still output the invoice header
    if not items:
        items = [{}]

    rows = []
    for item in items:
        row = {
            # ----- Invoice-level fields (repeated for each item) -----
            "invoice_number": invoice.get("invoice_number", ""),
            "vendor_name": invoice.get("vendor_name", ""),
            "vendor_tax_id": invoice.get("vendor_tax_id", ""),
            "vendor_address": invoice.get("vendor_address", ""),
            "client_name": invoice.get("client_name", ""),
            "invoice_date": invoice.get("invoice_date", ""),
            "due_date": invoice.get("due_date", ""),
            "currency": invoice.get("currency", ""),
            "subtotal": invoice.get("subtotal", ""),
            "tax_total": invoice.get("tax_total", ""),
            "total_amount_due": invoice.get("total_amount_due", ""),
            "iban": invoice.get("iban", ""),
            "notes": invoice.get("notes", ""),
            "category": invoice.get("category", ""),
            "confidence": invoice.get("confidence", ""),

            # ----- Item-level fields (specific to this line) -----
            "item_number": item.get("item_number", ""),
            "item_description": item.get("item_description", ""),
            "quantity": item.get("qty", 1),
            "unit_price": item.get("unit_price", ""),
            "tax_rate": item.get("tax_rate", ""),
            "tax_amount": item.get("tax_amount", ""),
            "line_total": item.get("line_total", ""),
        }
        rows.append(row)

    return rows
def convert_to_csv(results: List[Dict], errors: List[Dict], output_path: str) -> None:
    """
    Convert batch results into a clean, flattened CSV suitable for Excel/Google Sheets.

    Each line item of each invoice becomes a separate row. Invoice-level fields are repeated.
    If there are extraction errors, they are written to a separate `_errors.csv` file.

    Args:
        results: List of successful invoice dictionaries (already dumped from Pydantic).
        errors:  List of error dictionaries with keys "filename" and "error".
        output_path: Path where the main CSV will be saved.
    """
    # Step 1: Flatten every invoice into multiple rows
    all_rows = []
    for inv in results:
        all_rows.extend(flatten_invoice(inv))

    # Step 2: Define the column order (important for readability)
    # We'll use the keys from the first row if available, otherwise a sensible default.
    if all_rows:
        fieldnames = list(all_rows[0].keys())
    else:
        # Fallback header if no results at all
        fieldnames = [
            "invoice_number", "vendor_name", "invoice_date", "total_amount_due",
            "item_number", "item_description", "quantity", "unit_price", "line_total"
        ]

    # Step 3: Write the main CSV (even if empty, write the header)
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    # Step 4: Write errors to a separate file (optional but helpful)
    if errors:
        error_path = output_path.replace(".csv", "_errors.csv")
        with open(error_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=["filename", "error"])
            writer.writeheader()
            writer.writerows(errors)

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