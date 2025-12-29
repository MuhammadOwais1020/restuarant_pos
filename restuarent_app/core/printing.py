import win32print

# Default fallback printer
DEFAULT_PRINTER_NAME = "POS80 Printer"

def send_to_printer(raw_bytes: bytes, printer_name: str = None) -> None:
    """
    Open the Windows printer handle, send `raw_bytes` as a RAW job.
    Uses `printer_name` if provided, otherwise uses DEFAULT_PRINTER_NAME.
    """
    # 1. Use the specific name provided, otherwise fallback to default
    target_printer = printer_name if printer_name else DEFAULT_PRINTER_NAME

    # Debugging: check your console to see which printer is being targeted
    print(f"DEBUG: Attempting to print to: {target_printer}") 

    try:
        hprinter = win32print.OpenPrinter(target_printer)
        try:
            job_info = ("POS Print Job", None, "RAW")
            hjob = win32print.StartDocPrinter(hprinter, 1, job_info)
            win32print.StartPagePrinter(hprinter)
            win32print.WritePrinter(hprinter, raw_bytes)
            win32print.EndPagePrinter(hprinter)
            win32print.EndDocPrinter(hprinter)
        finally:
            win32print.ClosePrinter(hprinter)

    except Exception as e:
        print(f"CRITICAL PRINTER ERROR on {target_printer}: {e}")
        # We catch the error so the order still saves even if print fails