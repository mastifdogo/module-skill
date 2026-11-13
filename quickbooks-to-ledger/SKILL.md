---
name: quickbooks-to-ledger
description: Turn QuickBooks exports (a Journal report as CSV or Excel, an Account List, customer, vendor, invoice and bill lists, or a Desktop .IIF file) into a Ledger database dump (ledger.dump) that can be restored in Ledger, the self-hosted bookkeeping app (mastifdogo/Bookeeping), including the data of Ledger's modules (Sales customers and invoices, Auto sort bills). Use when someone uploads QuickBooks files and asks to move, migrate, convert or import their books into Ledger, or asks for a Ledger dump or backup file made from QuickBooks data.
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
- **Customers and vendors** (recommended): Reports → **Customer Contact
  List** and **Vendor Contact List**. They fill Ledger's own list of
  entities (each a customer, a vendor, or both), and let the converter tell
  who each transaction is with.
- **For Ledger's modules** (ask which modules they use; skip what they
  don't have installed):
  - *Sales module* (customers, invoices): Reports → **Customer Contact
    List**, and Reports → **Invoice List** (all dates; columns Date, Num,
    Customer, Due Date, Amount, Open Balance).
  - *Auto sort module* (bills it tracks until paid): Reports → **Unpaid
    Bills**, or **Transaction List by Vendor** for paid ones too.
  - A Desktop **IIF** export carries customers, invoices (with their
    lines) and bills already.
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

   Add the lists the user gave you:
   `--customers "Customer Contact List.csv" --vendors "Vendor Contact
   List.csv" --invoices "Invoice List.csv" --bills "Unpaid Bills.csv"`.

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
   - **sub-accounts**: QuickBooks' `Parent:Child` accounts become
     sub-accounts (`"parent"` holds the parent's code). Ledger needs a
     sub-account to have its parent's type and currency and allows 5
     levels; the converter flags the ones that don't fit and leaves them at
     the top level. A parent that only appeared in sub-account names is
     created with the type of what is under it: check it;
   - **account tags**: QuickBooks Bank accounts are tagged `chequing` (or
     `savings` when the detail type or name says so) and Credit Card
     accounts `credit_card`. Fix a wrong guess, or remove `"kind"`; the tag
     only fits asset accounts (chequing, savings) and liabilities (credit
     card);
   - **entities**: the customers and vendors found (from the lists, the
     invoices and bills, and the names on transactions). A name on both
     sides is one entity that is both. Merge spellings of the same business
     (`"Staples"` / `"STAPLES #114"`): keep one entity and point the
     entries at it. Names on transfers and journal entries that aren't a
     customer or vendor are left off; that is expected;
   - account codes: QuickBooks' own numbers are kept; accounts without one
     are numbered by type (1000s assets, 2000s liabilities, 3000s equity,
     4000s revenue, 5000s expenses). Renumber if the user has a scheme;
   - entries that don't balance: find why in the source (a missing split, a
     rounding difference, a foreign-currency line). Never add a plug line
     to make one balance without telling the user what you added and why.

   - the `"modules"` part, if any (see "Module data" below): customer
     details, each invoice's total, what is paid, and its lines.

4. **Check the totals against QuickBooks** before building:

   ```sh
   python3 scripts/build_dump.py books.json --check
   ```

   It prints the closing balance of each account type, and for the modules
   the invoices outstanding and bills owing: these should equal QuickBooks'
   Accounts Receivable and Accounts Payable balances (A/R and A/P aging
   totals). If they don't, some invoices or bills are missing from the
   lists, or partly paid ones are marked wrong.

   If the user gave a
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
   settings and other organizations are not touched. Needs Ledger 0.16.0 or
   later (an older Ledger refuses a dump from a newer one).

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
    { "code": "1000", "name": "Chequing", "type": "asset", "currency": "CAD", "description": "", "kind": "chequing" },
    { "code": "4000", "name": "Sales", "type": "revenue", "currency": "CAD" },
    { "code": "4010", "name": "Consulting", "type": "revenue", "currency": "CAD", "parent": "4000" }
  ],
  "entities": [
    { "name": "Globex Corp", "customer": true, "vendor": false, "email": "ap@globex.example", "phone": "", "address": "", "notes": "" }
  ],
  "entries": [
    { "date": "2026-01-15", "description": "Invoice - Globex Corp", "reference": "1001", "entity": "Globex Corp",
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
- `kind` (optional) tags a bank or card account: `chequing` or `savings`
  (asset accounts), `credit_card` (a liability).
- `entities` is Ledger's one list of customers and vendors; names are
  unique whatever the capitals, and each is a customer, a vendor or both.
  An entry's optional `entity` is one of those names: the vendor an expense
  was paid to, or the customer an entry is about.
- `parent` (optional) makes an account a sub-account of another: same type
  and currency, no loops, at most 5 levels. Entries can post to a parent
  and to its sub-accounts alike. Ledger's chart and statements then show
  the tree with a total for each parent.
- `date` is `YYYY-MM-DD`. Every entry needs a description and at least two
  lines, and must balance within each currency.
- An account's currency is CAD or USD and can't change later. Books in
  another currency, or with multi-currency transactions, don't fit Ledger:
  tell the user rather than converting amounts.

## Module data

`books.json` may carry data for Ledger's modules under `"modules"`. Only
include a module the user has installed in Ledger (the dump records the
module's tables as already created; Ledger brings them up to the installed
version on restore). The module must be installed **before** restoring.

```json
"modules": {
  "sales": {
    "customers": [
      { "name": "Globex Corp", "company": "", "email": "ap@globex.example", "phone": "", "address": "1 Volcano Way",
        "tax_id": "", "currency": "CAD", "terms_days": 30, "notes": "" }
    ],
    "invoices": [
      { "number": "1001", "customer": "Globex Corp", "issue_date": "2026-01-15", "due_date": "2026-02-14", "currency": "CAD",
        "total": 105000, "tax": 5000, "paid": 105000, "paid_date": "2026-01-20", "po_number": "", "notes": "",
        "lines": [{ "description": "Consulting January", "quantity": 10, "unit_price": 10000, "amount": 100000 }] }
    ]
  },
  "categorizer": {
    "bills": [
      { "vendor": "Hydro", "invoice_number": "H-1", "bill_date": "2026-01-25", "due_date": "2026-02-24", "amount": 12010,
        "currency": "CAD", "paid": false, "account": "6100", "ap_account": "2000", "summary": "January power" }
    ]
  }
}
```

- **Sales** (`sales`, module "Sales"): customers and invoices. An invoice's
  lines plus `tax` must equal `total`; `paid` is what has been received
  (fully paid invoices become "paid", the rest "open" with their balance).
  The invoice list report has no line detail, so each invoice gets one
  line for its whole amount with `tax` 0: if the user needs the lines and
  tax split, ask for **Sales by Customer Detail** and fill them in. When
  `paid_date` is missing the payment is dated the invoice date and marked
  so. New invoices in Ledger continue after the highest imported number.
  Invoices are history: their accounting is already in the journal entries,
  so they are not posted again.
- **Auto sort** (`categorizer`, module "Auto sort"): bills, open or paid.
  `ap_account` is the Accounts Payable account the bill sits in (the
  converter picks it when it can); `account` is the expense account, if
  known. Auto sort learns payee → account rules from the imported journal
  entries by itself; nothing to convert for that.
- **Import** (downloads), **Tailscale**, the example module and any other
  module: nothing in a QuickBooks export belongs to them. Their settings
  are made in Ledger and are not part of a dump.
- QuickBooks **vendors** as a list, **items/products**, **estimates** and
  **credit memos** have no place in the current modules: tell the user they
  were left out (credit memos' accounting is in the journal).

Check a module's tables against its repository if it has changed since this
skill was written (`assets/modules/<id>/MODULE_VERSION`): mastifdogo/
invoice-costumer-module (Sales), mastifdogo/llm-api-module (Auto sort).

## What does not come across

The chart of accounts (with sub-accounts and bank/card tags), the customers
and vendors, the journal entries, and the module data above.
Payroll details, attachments, bank feeds, reconciliations, items, vendors
as a list, estimates and recurring templates stay in QuickBooks (their
accounting effect is in the journal entries). Say this when you hand over
the file.
