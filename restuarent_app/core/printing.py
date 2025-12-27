# core/printing.py
import win32print

PRINTER_NAME = "POS80 Printer"  # ← exactly the name you see under Control Panel → Devices and Printers

def send_to_printer(raw_bytes: bytes) -> None:
    """
    Open the Windows printer handle, send `raw_bytes` as a RAW job,
    then close the printer. Raises on failure.
    """
    hprinter = win32print.OpenPrinter(PRINTER_NAME)
    try:
        job_info = ("POS Print Job", None, "RAW")
        hjob = win32print.StartDocPrinter(hprinter, 1, job_info)
        win32print.StartPagePrinter(hprinter)
        win32print.WritePrinter(hprinter, raw_bytes)
        win32print.EndPagePrinter(hprinter)
        win32print.EndDocPrinter(hprinter)
    finally:
        win32print.ClosePrinter(hprinter)
