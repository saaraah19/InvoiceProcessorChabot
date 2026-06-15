"""WHAT AN INVOICE LOOKS LIKE"""


from typing import List, Optional, Literal

from pydantic import BaseModel, Field


class Item(BaseModel):
    item_number: Optional[str] = Field(None, description="SKU or part number")
    item_description: Optional[str] = Field(None, description="Line item text description")
    qty: Optional[int] = Field(None, description="Quantity ordered/delivered")
    unit_price: Optional[float] = Field(None, description="Price per individual item excluding tax")
    tax_rate: Optional[float] = Field(None, description="Tax or VAT percentage applied to this line (e.g., 0.20 for 20%)")
    tax_amount: Optional[float] = Field(None, description="Calculated tax amount for this line")
    line_total: Optional[float] = Field(None, description="Total cost for this line item including tax")


class InvoiceData(BaseModel):
    filename: str
    confidence: float = Field(..., description="LLM extraction confidence score from 0.0 to 1.0")

    # Classification
    category: Optional[Literal[
        "Office Supplies", "Software & Subscriptions", "Travel",
        "Professional Services", "Utilities", "Meals & Entertainment", "Other"
    ]] = None
    invoice_description: Optional[str] = None

    # Vendor & Client Metadata
    vendor_name: Optional[str] = None
    vendor_tax_id: Optional[str] = Field(None, description="VAT number, EIN, or business registration number")
    vendor_address: Optional[str] = None
    client_name: Optional[str] = Field(None, description="The company or person being billed")

    # Payment / Banking Details
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = Field(None, description="Date issued. Prefer ISO format YYYY-MM-DD if possible")
    due_date: Optional[str] = Field(None, description="Payment due date")
    iban: Optional[str] = Field(None, description="Bank account routing number/IBAN")
    currency: Optional[str] = Field(None, description="3-letter currency code (e.g., USD, EUR, GBP)")

    # Financial Totals
    subtotal: Optional[float] = Field(None, description="Total before taxes and discounts")
    tax_total: Optional[float] = Field(None, description="Total tax amount across the invoice")
    total_amount_due: Optional[float] = Field(None, description="Grand total to be paid")

    # Nested Line Items
    items: Optional[List[Item]] = Field(None, alias="Items")  # Keeps snake_case in Python, accepts "Items" if mapped
    notes: Optional[str] = None