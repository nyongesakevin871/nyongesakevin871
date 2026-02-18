# Heart of Worship Restoration Center - Youth Payment CRM

A lightweight CRM system to register youth members and track/manage their payments.

## Features

- Dashboard with key totals:
  - Total registered youths
  - Total contributions
  - Monthly contributions
- Youth member management:
  - Add members with name, gender, phone, and zone/cell
  - View members with cumulative amount paid
- Payment management:
  - Record payments by type (tithe, offering, seed, project contribution)
  - Track date, amount, method, and notes
  - View payment history
  - Delete incorrect payment records

## Quick start

```bash
python3 app.py
```

Then open http://127.0.0.1:5000 in your browser.

## Data storage

The app uses SQLite and automatically creates `crm.db` in the project root on first run.
