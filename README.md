# oil_workshop (Odoo 17)

Module created for Muhammad Ali.

Features:
- Shift management (open/close)
- Link oil.work.order to shifts automatically
- Expenses tied to shifts
- Thermal (80mm) and formal A4 reports
- Security groups: User / Manager / Admin

Installation:
1. Copy this module to your Odoo addons folder.
2. Update apps list and install.
3. Assign users to groups: Oil Workshop / User, Manager, Admin.

Notes:
- Adapt view inheritance for oil.work.order if your original module has different view ids.
- Thermal printing: configure IoT/Printer to print the PDF to your 80mm thermal printer.
