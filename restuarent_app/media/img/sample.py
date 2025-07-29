import os
import pdfkit

def print_invoice_html(order):
    html_content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; }}
            .invoice-header {{ text-align: center; }}
            .invoice-body {{ margin-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="invoice-header">
            <img src="path_to_logo.png" alt="Logo" width="100" />
            <h1>MR FOOD</h1>
        </div>
        <div class="invoice-body">
            <p>Order #: {order.number}</p>
            <p>Date: {order.created_at.strftime('%Y-%m-%d %H:%M')}</p>
            <!-- Add more order details here -->
        </div>
    </body>
    </html>
    """
    
    pdfkit.from_string(html_content, "invoice.pdf")
    # Now print the PDF using your system's default printing mechanism
    # For example, you could use the `lp` command in Linux or print directly in Windows
    os.system("lp invoice.pdf")
