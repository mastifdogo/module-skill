---
name: quickbooks-to-ledger
description: Turn a QuickBooks export (a Journal report as CSV or Excel, an Account List, or a Desktop .IIF file) into a Ledger database dump (ledger.dump) that can be restored in Ledger, the self-hosted bookkeeping app (mastifdogo/Bookeeping). Use when someone uploads QuickBooks files and asks to move, migrate, convert or import their books into Ledger, or asks for a Ledger dump or backup file made from QuickBooks data.
---

# QuickBooks to a Ledger dump

The user uploads QuickBooks exports; you hand back `ledger.dump`. They
restore it in Ledger under **Settings → Backups → Restore from a backup →
upload a dump file**, in the organization whose books it should become.
That restore replaces that organization's books, so say so when you hand the
file over.

Paths below are relative to this skill's folder.

## What you need from the user

- **The transactions**: QuickBooks Online: Reports → **Journal**, report
  period **All Dates**, Export to Excel or CSV. QuickBooks Desktop: Reports →
  Accountant & Taxes → **Journal** (all dates) exported to Excel/CSV, or
  File → Utilities → Export → **IIF** files.
- **The chart of accounts** (strongly recommended, it carries each account's
  type): Online: Settings ⚙ → Chart of accounts → Run report → export
  (the "Account List"). An IIF file already has it.
- **The currency** of the books: Ledger keeps CAD and USD. If they didn't
  say and the file doesn't show it, ask.

A General Ledger, Transaction List, Profit and Loss or Balance Sheet report
is not enough on its own: those show one side of each transaction or only
totals. If that is all they uploaded, ask for the Journal report. Don't
invent the other side of transactions.

## Steps

1. **Look at the files first.** Open each one and read the first 30 lines
   (for Excel, load it with openpyxl): which report it is, the header row,
   how dates and amounts are written, whether accounts have numbers.

2. **Convert** to a `books.json` you can read and correct:

   ```sh
   python3 scripts/qb_convert.py "Journal.csv" --accounts "Account List.csv" \
     --currency CAD --source "QuickBooks Online, <company>" -o books.json
   ```

   Several journal or IIF files can be given at once. `--date-format dmy`
   or `mdy` settles how `03/04/2026` reads when the file can't. If the
   script can't read a file's layout, don't force it: write `books.json`
   yourself from the file (format below) with a short script of your own.

3. **Review `books.json`**, and fix it by editing the file (or the source
   and converting again):
   - everything the converter printed under TO REVIEW (also in the file's
     `"review"` list);
   - **every account's `type`**: asset, liability, equity, revenue or
     expense. QuickBooks types map as: Bank, Accounts receivable, current/
     fixed/other assets → asset; Accounts payable, Credit card, current and
     long-term liabilities → liability; Equity → equity; Income, Other
     income → revenue; Expenses, Other expense, Cost of goods sold →
     expense. A wrong type puts the account on the wrong report;
   - account codes: QuickBooks' own numbers are kept; accounts without one
     are numbered by type (1000s assets, 2000s liabilities, 3000s equity,
     4000s revenue, 5000s expenses). Renumber if the user has a scheme;
   - entries that don't balance: find why in the source (a missing split, a
     rounding difference, a foreign-currency line). Never add a plug line
     to make one balance without telling the user what you added and why.

4. **Check the totals against QuickBooks** before building:

   ```sh
   python3 scripts/build_dump.py books.json --check
   ```

   It prints the closing balance of each account type. If the user gave a
   Trial Balance or Balance Sheet, compare: total assets, liabilities and
   equity should match as of the last entry's date. Tell the user about any
   difference instead of hiding it.

5. **Build the dump**:

   ```sh
   python3 scripts/build_dump.py books.json -o ledger.dump
   ```

   This starts a throwaway PostgreSQL, creates Ledger's schema
   (`assets/ledger-db`), loads the books (the database itself refuses an
   entry that doesn't balance), runs `pg_dump` and checks the result with
   `pg_restore --list`.

6. **Hand over `ledger.dump`** with: how many accounts and entries it holds
   and the date range; anything you changed, guessed or left out; and the
   restore steps: in Ledger, switch to the organization the books belong in
   (an admin of the main books can create a new one under Settings → Users),
   then Settings → Backups → Restore from a backup → Choose a backup to
   restore → upload the file → select it → type RESTORE. Ledger backs up
   that organization's current books first, then replaces them. Users,
   settings and other organizations are not touched. Needs Ledger 0.14.2 or
   later.

## PostgreSQL version

A dump can only be read by a `pg_restore` that is the same major version as
the `pg_dump` that wrote it, or newer. Ledger's server (its Debian 12
container) runs **PostgreSQL 15**, so the dump must be written by PostgreSQL
15: `build_dump.py` looks for it on this machine and otherwise downloads it
from PyPI (`postgresql-binaries`, PostgreSQL built for Linux and macOS) into
a temporary folder. If neither works (no network to PyPI, an unsupported
platform), it stops and says so. Then tell the user plainly that this
environment can't write the dump, give them `books.json`, and offer the
alternative that needs no dump: Ledger's own **Settings → Import & export →
Migrate** takes the same QuickBooks exports directly. Don't hand over a dump
made with a newer PostgreSQL unless the user says their server runs that
version (`--pg-version 16`): Ledger would refuse it.

## books.json

```json
{
  "ledger_books": 1,
  "source": "QuickBooks Online, Acme Inc.",
  "accounts": [
    { "code": "1000", "name": "Chequing", "type": "asset", "currency": "CAD", "description": "" }
  ],
  "entries": [
    { "date": "2026-01-15", "description": "Invoice - Globex Corp", "reference": "1001",
      "lines": [
        { "account": "1200", "debit": 105000, "memo": "Consulting January" },
        { "account": "4000", "credit": 100000, "memo": "" },
        { "account": "2100", "credit": 5000, "memo": "GST" }
      ] }
  ]
}
```

- Amounts are **whole cents** (integers): $1,050.00 is `105000`. Each line
  has a `debit` or a `credit`, never both.
- `account` is an account's `code`. Codes are 1-32 letters, digits, `.`,
  `_` or `-`.
- `date` is `YYYY-MM-DD`. Every entry needs a description and at least two
  lines, and must balance within each currency.
- An account's currency is CAD or USD and can't change later. Books in
  another currency, or with multi-currency transactions, don't fit Ledger:
  tell the user rather than converting amounts.

## What does not come across

Only the chart of accounts and the journal entries. Customers, vendors,
open invoices and bills as documents, items, payroll details, attachments,
bank feeds and reconciliations stay in QuickBooks (their accounting effect
is in the journal entries). Say this when you hand over the file.
