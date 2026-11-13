#!/usr/bin/env python3
"""Turns QuickBooks exports into a books.json for build_dump.py.

Reads, in any combination:
  * a Journal report (QuickBooks Online or Desktop: Reports -> Journal, all
    dates, exported to CSV or Excel): the transactions
  * an Account List / Chart of Accounts export (CSV or Excel): account types
    and numbers
  * an .IIF file (QuickBooks Desktop): accounts and transactions

  python3 qb_convert.py Journal.csv --accounts "Account List.csv" -o books.json
  python3 qb_convert.py company.iif -o books.json

books.json is meant to be read and corrected (by you or by Claude) before
build_dump.py makes the dump: check every account's "type", and anything
listed under "review".
"""
import argparse
import csv
import io
import json
import re
import sys
from collections import OrderedDict
from datetime import date

TYPES = ("asset", "liability", "equity", "revenue", "expense")
# QuickBooks account types (Online and Desktop/IIF) -> Ledger's five.
QB_TYPES = {
    "bank": "asset", "accounts receivable": "asset", "accounts receivable (a/r)": "asset", "ar": "asset",
    "other current asset": "asset", "other current assets": "asset", "current assets": "asset", "ocasset": "asset",
    "fixed asset": "asset", "fixed assets": "asset", "fixasset": "asset", "property, plant and equipment": "asset",
    "other asset": "asset", "other assets": "asset", "oasset": "asset", "non-current assets": "asset", "cash and cash equivalents": "asset",
    "accounts payable": "liability", "accounts payable (a/p)": "liability", "ap": "liability",
    "credit card": "liability", "ccard": "liability", "other current liability": "liability",
    "other current liabilities": "liability", "current liabilities": "liability", "ocliab": "liability",
    "long term liability": "liability", "long term liabilities": "liability", "ltliab": "liability", "non-current liabilities": "liability",
    "equity": "equity", "owner's equity": "equity",
    "income": "revenue", "other income": "revenue", "inc": "revenue", "exinc": "revenue", "revenue": "revenue",
    "expense": "expense", "expenses": "expense", "other expense": "expense", "exp": "expense", "exexp": "expense",
    "cost of goods sold": "expense", "cogs": "expense", "cost of sales": "expense",
}
# When no account list says, guess from the name; these are listed under "review".
NAME_HINTS = [
    (r"receivable|chequing|checking|savings|bank|cash|inventory|prepaid|undeposited|equipment|vehicle|furniture|deposit paid|accumulated", "asset"),
    (r"payable|credit card|visa|mastercard|amex|loan|line of credit|mortgage|gst|hst|pst|qst|sales tax|vat|payroll liabilit|unearned|deferred revenue", "liability"),
    (r"equity|retained earnings|owner|capital|drawings?|draws?|dividends? paid|opening balance", "equity"),
    (r"sales|income|revenue|fees earned|interest earned|discounts? received", "revenue"),
]
RANGES = {"asset": 1000, "liability": 2000, "equity": 3000, "revenue": 4000, "expense": 5000}


def norm(s):
    return re.sub(r"[^a-z0-9#]+", " ", str(s or "").lower()).strip()


def read_table(path):
    """Rows (lists of text) from a CSV, TSV or Excel file."""
    if path.lower().endswith((".xlsx", ".xlsm")):
        try:
            import openpyxl
        except ImportError:
            sys.exit(f"{path}: reading Excel needs openpyxl (pip install openpyxl), or export the report as CSV")
        ws = openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[0]
        out = []
        for row in ws.iter_rows(values_only=True):
            out.append(["" if c is None else (c.strftime("%Y-%m-%d") if hasattr(c, "strftime") else str(c)) for c in row])
        return out
    if path.lower().endswith(".xls"):
        sys.exit(f"{path}: old .xls files can't be read; export the report as CSV or .xlsx")
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeError:
            continue
    first = text.split("\n", 1)[0]
    delim = "\t" if first.count("\t") > first.count(",") else (";" if first.count(";") > first.count(",") else ",")
    return [[c.strip() for c in r] for r in csv.reader(io.StringIO(text), delimiter=delim)]


def money(s):
    """Text -> whole cents (int), or None when empty."""
    t = str(s or "").strip().replace("−", "-")
    if t in ("", "-"):
        return None
    neg = t.startswith("(") and t.endswith(")")
    t = re.sub(r"[^0-9.,-]", "", t)
    if t.count(",") and t.count(".") == 0 and re.search(r",\d{1,2}$", t):
        t = t.replace(".", "").replace(",", ".")  # 1.234,56 / 12,5
    else:
        t = t.replace(",", "")
    if t in ("", "-", "."):
        return None
    neg = neg or t.startswith("-")
    whole, _, frac = t.lstrip("-").partition(".")
    cents = int(whole or "0") * 100 + int((frac + "00")[:2]) + (1 if len(frac) > 2 and frac[2] >= "5" else 0)
    return -cents if neg else cents


def parse_date(s, fmt):
    t = str(s or "").strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
    else:
        m = re.match(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})$", t)
        if not m:
            return None
        a, b, y = int(m[1]), int(m[2]), int(m[3])
        y += 2000 if y < 70 else (1900 if y < 100 else 0)
        mo, d = (a, b) if fmt == "mdy" else (b, a)
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def guess_date_format(values):
    firsts = [int(m[1]) for m in (re.match(r"^(\d{1,2})[/.-](\d{1,2})[/.-]\d{2,4}$", v.strip()) for v in values) if m]
    seconds = [int(m[2]) for m in (re.match(r"^(\d{1,2})[/.-](\d{1,2})[/.-]\d{2,4}$", v.strip()) for v in values) if m]
    if any(x > 12 for x in firsts):
        return "dmy", True
    if any(x > 12 for x in seconds):
        return "mdy", True
    return "mdy", False  # can't tell: QuickBooks' US default


class Books:
    def __init__(self, currency):
        self.currency = currency
        self.accounts = OrderedDict()  # QuickBooks name -> {code?, name, type?, description, guessed}
        self.entries = []
        self.review = []

    def account(self, qb_name, type_=None, number=None, description=""):
        full = re.sub(r"\s*:\s*", ":", str(qb_name).strip())
        # "1000 Chequing" / "1000 · Chequing": the number is part of the name.
        m = re.match(r"^(\d{3,8})\s*[·\-–: ]\s*(.+)$", full.split(":")[-1]) if not number else None
        key = full.lower()
        a = self.accounts.get(key)
        if not a:
            a = self.accounts[key] = {"qb_name": full, "name": (m[2] if m else full.split(":")[-1]).strip()[:200], "number": number or (m[1] if m else ""), "type": None, "description": description}
            if ":" in full:
                a["description"] = a["description"] or f"QuickBooks: {full}"
        if type_ and not a["type"]:
            a["type"] = type_
        if number and not a["number"]:
            a["number"] = number
        return key

    def finish(self):
        used = set()
        counters = dict(RANGES)
        out = []
        for a in self.accounts.values():
            if not a["type"]:
                a["type"] = next((t for pat, t in NAME_HINTS if re.search(pat, a["qb_name"].lower())), "expense")
                self.review.append(f'account "{a["qb_name"]}": type guessed as {a["type"]} (no account list said); check it')
        # Accounts with a QuickBooks number keep it; the rest are numbered by type.
        for a in self.accounts.values():
            code = re.sub(r"[^A-Za-z0-9._-]", "", a["number"])[:32]
            if code and code not in used:
                a["code"] = code
                used.add(code)
        for a in self.accounts.values():
            if "code" not in a:
                n = counters[a["type"]]
                while str(n) in used:
                    n += 10
                a["code"] = str(n)
                used.add(a["code"])
                counters[a["type"]] = n + 10
            out.append({"code": a["code"], "name": a["name"], "type": a["type"], "currency": self.currency, "description": a["description"]})
        codes = {k: a["code"] for k, a in self.accounts.items()}
        for e in self.entries:
            for l in e["lines"]:
                l["account"] = codes[l.pop("_key")]
        return out


def find_header(rows, need):
    for i, r in enumerate(rows[:40]):
        cells = [norm(c) for c in r]
        if all(any(c == n or c.startswith(n) for c in cells) for n in need):
            return i, cells
    return None, None


def col(cells, *names):
    for n in names:
        for i, c in enumerate(cells):
            if c == n:
                return i
    for n in names:
        for i, c in enumerate(cells):
            if c.startswith(n):
                return i
    return None


def read_account_list(path, books):
    rows = read_table(path)
    h, cells = find_header(rows, ["type"])
    if h is None:
        sys.exit(f"{path}: no header row with a Type column; is this the Account List export?")
    c_name = col(cells, "account", "full name", "name", "account name")
    c_type = col(cells, "type", "account type")
    c_num = col(cells, "account #", "number", "account number", "no", "#")
    c_desc = col(cells, "description")
    if c_name is None:
        sys.exit(f"{path}: no Account / Name column")
    n = 0
    for r in rows[h + 1:]:
        get = lambda i: r[i].strip() if i is not None and i < len(r) else ""
        name, t = get(c_name), QB_TYPES.get(norm(get(c_type)).replace(" a r", " (a/r)").replace(" a p", " (a/p)")) or QB_TYPES.get(get(c_type).strip().lower())
        if not name or name.lower().startswith("total"):
            continue
        key = books.account(name, t, get(c_num), get(c_desc))
        if not t and get(c_type):
            books.review.append(f'account "{name}": QuickBooks type "{get(c_type)}" is not one I know; set its type')
        n += 1
    return n


def read_journal(path, books, date_format):
    rows = read_table(path)
    h, cells = find_header(rows, ["account", "debit", "credit"])
    if h is None:
        sys.exit(f"{path}: no header row with Account, Debit and Credit columns. Export Reports -> Journal (not General Ledger or Transaction List), all dates.")
    c_date = col(cells, "date", "transaction date", "trans date")
    c_type = col(cells, "transaction type", "type")
    c_num = col(cells, "num", "no", "number", "ref no", "doc num", "trans #")
    c_name = col(cells, "name", "payee", "customer", "vendor")
    c_memo = col(cells, "memo description", "memo", "description", "line description")
    c_acc, c_dr, c_cr = col(cells, "account", "full name", "account full name"), col(cells, "debit"), col(cells, "credit")
    body = rows[h + 1:]
    get = lambda r, i: r[i].strip() if i is not None and i < len(r) else ""
    if not date_format:
        date_format, sure = guess_date_format([get(r, c_date) for r in body])
        if not sure and any(re.match(r"^\d{1,2}[/.-]", get(r, c_date)) for r in body):
            books.review.append(f"dates read as month/day/year (no date in the file settles it); pass --date-format dmy if the file is day/month/year")
    cur = None

    def close():
        nonlocal cur
        if cur and cur["lines"]:
            books.entries.append(cur)
        cur = None

    for n, r in enumerate(body, start=h + 2):
        if not any(c.strip() for c in r):
            close()
            continue
        d = parse_date(get(r, c_date), date_format)
        acc, dr, cr = get(r, c_acc), money(get(r, c_dr)), money(get(r, c_cr))
        first = " ".join(c for c in r if c.strip()).lower()
        if not acc and (first.startswith("total") or dr is not None or cr is not None):
            close()  # a transaction's total line
            continue
        if d:
            close()
            parts = [get(r, c_type), get(r, c_name)]
            cur = {"date": d, "description": " - ".join(p for p in parts if p)[:500], "reference": get(r, c_num)[:100], "lines": [], "_row": n, "_memo": get(r, c_memo)}
        elif get(r, c_date) and not acc:
            continue  # titles, "Cash basis", page footers
        if not acc or cur is None or (dr is None and cr is None):
            continue
        amount = (dr or 0) - (cr or 0)
        if amount == 0:
            continue
        key = books.account(acc)
        line = {"_key": key, "memo": get(r, c_memo)[:500]}
        line["debit" if amount > 0 else "credit"] = abs(amount)
        cur["lines"].append(line)
    close()


def read_iif(path, books, date_format):
    rows = read_table(path)
    heads = {}
    cur = None
    fmt = date_format or "mdy"
    for r in rows:
        if not r or not r[0]:
            continue
        tag = r[0]
        if tag.startswith("!"):
            heads[tag[1:]] = [c.upper() for c in r]
            continue
        hd = heads.get(tag)
        if not hd:
            continue
        f = lambda k: (r[hd.index(k)].strip() if k in hd and hd.index(k) < len(r) else "")
        if tag == "ACCNT":
            t = QB_TYPES.get(f("ACCNTTYPE").lower())
            books.account(f("NAME"), t, f("ACCNUM"), f("DESC"))
            if not t:
                books.review.append(f'account "{f("NAME")}": QuickBooks type "{f("ACCNTTYPE")}" is not one I know; set its type')
        elif tag in ("TRNS", "SPL"):
            if tag == "TRNS":
                d = parse_date(f("DATE"), fmt)
                if not d:
                    books.review.append(f'transaction dated "{f("DATE")}" skipped: the date could not be read')
                    cur = None
                    continue
                cur = {"date": d, "description": " - ".join(p for p in (f("TRNSTYPE"), f("NAME")) if p)[:500], "reference": f("DOCNUM")[:100], "lines": [], "_memo": f("MEMO")}
            if cur is None:
                continue
            amount = money(f("AMOUNT"))  # IIF: positive = debit
            if amount:
                line = {"_key": books.account(f("ACCNT")), "memo": f("MEMO")[:500]}
                line["debit" if amount > 0 else "credit"] = abs(amount)
                cur["lines"].append(line)
        elif tag == "ENDTRNS":
            if cur and cur["lines"]:
                books.entries.append(cur)
            cur = None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="Journal report (CSV/XLSX) and/or .IIF files")
    ap.add_argument("--accounts", action="append", default=[], help="Account List / Chart of Accounts export (CSV/XLSX)")
    ap.add_argument("--currency", default="CAD", choices=["CAD", "USD"], help="the books' currency (Ledger keeps CAD and USD)")
    ap.add_argument("--date-format", choices=["mdy", "dmy"], help="how 03/04/2026 reads; default: worked out from the file, else mdy")
    ap.add_argument("--source", default="", help='a note kept in the file, e.g. "QuickBooks Online, Acme Inc."')
    ap.add_argument("-o", "--output", default="books.json")
    a = ap.parse_args()

    books = Books(a.currency)
    for p in a.accounts:
        n = read_account_list(p, books)
        print(f"{p}: {n} accounts")
    for p in a.files:
        before = len(books.entries)
        (read_iif if p.lower().endswith(".iif") else read_journal)(p, books, a.date_format)
        print(f"{p}: {len(books.entries) - before} transactions")

    accounts = books.finish()
    entries = []
    for e in books.entries:
        memo = e.pop("_memo", "")
        row = e.pop("_row", None)
        if not e["description"]:
            e["description"] = memo[:500] or "(no description)"
        total = sum(l.get("debit", 0) - l.get("credit", 0) for l in e["lines"])
        where = f'{e["date"]} {e["description"][:50]!r}' + (f" (row {row})" if row else "")
        if total != 0:
            books.review.append(f"entry {where} is out of balance by {total / 100:.2f}: fix it in the source or in books.json (build_dump.py refuses unbalanced entries)")
        if len(e["lines"]) < 2:
            books.review.append(f"entry {where} has fewer than two lines")
        entries.append(e)
    entries.sort(key=lambda e: e["date"])

    doc = {"ledger_books": 1, "source": a.source or "QuickBooks: " + ", ".join(a.files), "accounts": accounts, "entries": entries, "review": books.review}
    with open(a.output, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)

    print(f"\nwrote {a.output}: {len(accounts)} accounts, {len(entries)} entries" + (f", {entries[0]['date']} to {entries[-1]['date']}" if entries else ""))
    by = {t: sum(1 for x in accounts if x["type"] == t) for t in TYPES}
    print("accounts by type: " + ", ".join(f"{n} {t}" for t, n in by.items()))
    if books.review:
        print(f"\nTO REVIEW ({len(books.review)}):")
        for r in books.review[:60]:
            print("  - " + r)
        if len(books.review) > 60:
            print(f"  ... and {len(books.review) - 60} more (all are in {a.output} under \"review\")")
    else:
        print("nothing flagged for review; still read the account types before building")


if __name__ == "__main__":
    main()
