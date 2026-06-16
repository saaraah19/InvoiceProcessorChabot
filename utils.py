def sanitize_cell(value):
    """
    Prevent CSV/Excel formula injection from data extracted out of
    user-uploaded invoices.

    If a string value starts with =, +, -, or @, spreadsheet apps
    (Excel, Google Sheets, LibreOffice) may interpret it as a formula
    when the exported file is opened. Prefixing with a single quote
    forces it to be treated as plain text.
    """
    if isinstance(value, str) and value and value[0] in ("=", "+", "-", "@"):
        return "'" + value
    return value