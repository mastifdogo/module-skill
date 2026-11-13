#!/usr/bin/env python3
"""Builds a Ledger database dump (ledger.dump) from a books.json.

  python3 build_dump.py books.json -o ledger.dump

The dump is what Ledger's backups contain: upload it under Settings ->
Backups -> Restore from a backup -> "upload a dump file" (Ledger 0.16.0 or
later), in the organization whose books it should become.

It is made by a real PostgreSQL: the script starts a throwaway server in a
temporary folder, creates Ledger's schema (assets/ledger-db), loads the
accounts and entries, and runs pg_dump. The database's own rules check every
entry balances.

PostgreSQL must not be newer than the one Ledger's server runs (Ledger's
Debian 12 container has PostgreSQL 15): pg_restore can't read a dump made by
a newer pg_dump. The script looks for PostgreSQL 15 on this machine and,
failing that, installs it from PyPI (the postgresql-binaries package).
"""
import argparse
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB_DIR = HERE.parent / "assets" / "ledger-db"
TYPES = ("asset", "liability", "equity", "revenue", "expense")
KIND_TYPE = {"chequing": "asset", "savings": "asset", "credit_card": "liability"}
CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")


def die(msg):
    sys.exit("error: " + msg)


# ---------------------------------------------------------------------------
# The books
# ---------------------------------------------------------------------------

def check_books(doc):
    """Returns (accounts, entries) or stops with every problem found (up to 40)."""
    problems = []
    bad = problems.append
    if not isinstance(doc, dict) or doc.get("ledger_books") != 1:
        die('not a books file (it needs "ledger_books": 1)')
    accounts, seen = [], {}
    for i, a in enumerate(doc.get("accounts") or [], 1):
        code, name = str(a.get("code", "")).strip(), str(a.get("name", "")).strip()
        if not CODE_RE.match(code):
            bad(f"account {i}: code {code!r} must be 1-32 letters, digits, '.', '_' or '-'")
        elif code in seen:
            bad(f"account {i}: code {code} is used twice")
        if not name:
            bad(f"account {i} ({code}): name is missing")
        if a.get("type") not in TYPES:
            bad(f"account {i} ({code} {name}): type must be one of {', '.join(TYPES)}")
        if a.get("currency") not in ("CAD", "USD"):
            bad(f"account {i} ({code} {name}): currency must be CAD or USD")
        seen[code] = a.get("currency")
        kind = a.get("kind") or None
        if kind is not None and KIND_TYPE.get(kind) != a.get("type"):
            bad(f"account {i} ({code} {name}): kind must be chequing or savings (asset accounts) or credit_card (a liability)")
        accounts.append({"code": code, "name": name[:200], "type": a.get("type"), "currency": a.get("currency"), "description": str(a.get("description") or "").strip()[:1000],
                         "parent": str(a.get("parent") or "").strip() or None, "kind": kind})
    if not accounts:
        die("the books file has no accounts")
    # Sub-accounts: the parent exists, is the same type and currency, no loops, at most 5 levels.
    by = {a["code"]: a for a in accounts}
    for a in accounts:
        p = by.get(a["parent"]) if a["parent"] else None
        if a["parent"] and not p:
            bad(f"account {a['code']} {a['name']}: there is no parent account {a['parent']!r}")
        elif p and (p["type"] != a["type"] or p["currency"] != a["currency"]):
            bad(f"account {a['code']} {a['name']}: its parent {p['code']} must have the same type and currency")
        depth, up, loop = 1, p, False
        while up:
            depth += 1
            if up is a or depth > 50:
                loop = True
                break
            up = by.get(up["parent"]) if up["parent"] else None
        if loop:
            bad(f"account {a['code']} {a['name']}: it is under itself (a loop of parents)")
        elif depth > 5:
            bad(f"account {a['code']} {a['name']}: accounts can be nested at most 5 levels deep")
    # Entities: Ledger's one list of customers and vendors (an entity can be both).
    entities, names = [], {}
    for i, x in enumerate(doc.get("entities") or [], 1):
        nm = re.sub(r"\s+", " ", str(x.get("name") or "")).strip()[:200]
        if not nm:
            bad(f"entity {i}: name is missing")
            continue
        if nm.lower() in names:
            bad(f"entity {i}: {nm!r} is listed twice (names are unique whatever the capitals; mark one as both customer and vendor)")
        if not (x.get("customer") is True or x.get("vendor") is True):
            bad(f"entity {i} ({nm}): must be a customer, a vendor or both")
        names[nm.lower()] = nm
        entities.append({"name": nm, "customer": x.get("customer") is True, "vendor": x.get("vendor") is True,
                         **{k: str(x.get(k) or "").strip()[:n] for k, n in (("email", 200), ("phone", 100), ("address", 1000), ("notes", 2000))}})
    entries = []
    for i, e in enumerate(doc.get("entries") or [], 1):
        d = str(e.get("date", ""))
        at = f"entry {i} ({d} {str(e.get('description', ''))[:40]!r})"
        try:
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
                raise ValueError
            date.fromisoformat(d)
        except ValueError:
            bad(f"{at}: date must be YYYY-MM-DD")
        desc = str(e.get("description") or "").strip()[:500]
        if not desc:
            bad(f"{at}: description is missing")
        lines, totals = [], {}
        for j, l in enumerate(e.get("lines") or [], 1):
            code = str(l.get("account", "")).strip()
            if code not in seen:
                bad(f"{at} line {j}: there is no account {code!r}")
                continue
            dr, cr = l.get("debit") or 0, l.get("credit") or 0
            if not (isinstance(dr, int) and isinstance(cr, int) and not isinstance(dr, bool) and dr >= 0 and cr >= 0):
                bad(f"{at} line {j}: debit and credit must be whole cents (integers)")
                continue
            if (dr > 0) == (cr > 0):
                bad(f"{at} line {j}: needs a debit or a credit, not both and not neither")
                continue
            totals[seen[code]] = totals.get(seen[code], 0) + dr - cr
            lines.append({"account": code, "amount": dr - cr, "memo": str(l.get("memo") or "").strip()[:500]})
        if len(lines) < 2:
            bad(f"{at}: needs at least two lines")
        for cur, t in totals.items():
            if t != 0:
                bad(f"{at}: out of balance by {t / 100:.2f} {cur}")
        ent = re.sub(r"\s+", " ", str(e.get("entity") or "")).strip()
        if ent and ent.lower() not in names:
            bad(f"{at}: entity {ent!r} is not in the entities list")
        entries.append({"date": d, "description": desc, "reference": str(e.get("reference") or "").strip()[:100], "lines": lines, "entity": names.get(ent.lower()) if ent else None})
        if len(problems) >= 40:
            break
    if problems:
        die("the books file has problems:\n  - " + "\n  - ".join(problems) + ("\n  ..." if len(problems) >= 40 else ""))
    return accounts, entries, entities


MODULES = {"sales": "mod_sales", "categorizer": "mod_categorizer"}  # module id -> its schema
MODULES_DIR = HERE.parent / "assets" / "modules"


def iso(d):
    try:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(d)):
            return False
        date.fromisoformat(d)
        return True
    except ValueError:
        return False


def cents_ok(n, positive=False):
    return isinstance(n, int) and not isinstance(n, bool) and (n > 0 if positive else True) and abs(n) < 10**15


def check_modules(doc, account_codes):
    """Checks the optional "modules" part; returns it cleaned, or stops with the problems."""
    mods = doc.get("modules") or {}
    problems = []
    bad = problems.append
    for k in mods:
        if k not in MODULES:
            bad(f'modules: there is no module "{k}" (known: {", ".join(MODULES)})')
    out = {}
    sales = mods.get("sales") or {}
    if sales.get("customers") or sales.get("invoices"):
        customers, names = [], {}
        for i, c in enumerate(sales.get("customers") or [], 1):
            name = str(c.get("name") or "").strip()[:200]
            if not name:
                bad(f"sales customer {i}: name is missing")
                continue
            if name.lower() in names:
                bad(f"sales customer {i}: {name!r} is listed twice")
            names[name.lower()] = True
            cur = c.get("currency") or "CAD"
            if cur not in ("CAD", "USD"):
                bad(f"sales customer {name!r}: currency must be CAD or USD")
            terms = c.get("terms_days")
            if terms is not None and not (isinstance(terms, int) and 0 <= terms <= 365):
                bad(f"sales customer {name!r}: terms_days must be 0 to 365")
            customers.append({"name": name, "currency": cur, "terms_days": terms, **{k: str(c.get(k) or "").strip()[:2000] for k in ("company", "email", "phone", "address", "tax_id", "notes")}})
        invoices, numbers = [], {}
        for i, v in enumerate(sales.get("invoices") or [], 1):
            num = str(v.get("number") or "").strip()[:60]
            at = f"sales invoice {i} ({num})"
            cust = str(v.get("customer") or "").strip()
            if not num:
                bad(f"{at}: number is missing")
            elif num.lower() in numbers:
                bad(f"{at}: number is used twice")
            numbers[num.lower()] = True
            if cust.lower() not in names:
                bad(f"{at}: customer {cust!r} is not in the customers list")
            if not iso(v.get("issue_date")) or not iso(v.get("due_date")) or v["due_date"] < v["issue_date"]:
                bad(f"{at}: issue_date and due_date must be YYYY-MM-DD, due on or after issue")
            total, tax, paid = v.get("total"), v.get("tax") or 0, v.get("paid") or 0
            if not cents_ok(total, True) or not cents_ok(tax) or tax < 0 or not cents_ok(paid) or paid < 0:
                bad(f"{at}: total (> 0), tax and paid must be whole cents")
                continue
            if paid > total:
                bad(f"{at}: paid is more than the total")
            if v.get("paid_date") and not iso(v.get("paid_date")):
                bad(f"{at}: paid_date must be YYYY-MM-DD")
            if v.get("currency") not in ("CAD", "USD"):
                bad(f"{at}: currency must be CAD or USD")
            lines = []
            for j, l in enumerate(v.get("lines") or [], 1):
                desc = str(l.get("description") or "").strip()[:1000]
                qty = l.get("quantity", 1)
                if not desc or not isinstance(qty, (int, float)) or isinstance(qty, bool) or qty <= 0 or not cents_ok(l.get("unit_price")) or not cents_ok(l.get("amount")):
                    bad(f"{at} line {j}: needs a description, a quantity above 0, and unit_price and amount in whole cents")
                    continue
                lines.append({"description": desc, "quantity": max(1, round(qty * 1000)), "unit_price": l["unit_price"], "amount": l["amount"]})
            if not lines:
                bad(f"{at}: needs at least one line")
            elif sum(l["amount"] for l in lines) + tax != total:
                bad(f"{at}: its lines ({sum(l['amount'] for l in lines) / 100:.2f}) plus tax ({tax / 100:.2f}) don't add up to the total ({total / 100:.2f})")
            invoices.append({"number": num, "customer": cust, "issue_date": v.get("issue_date"), "due_date": v.get("due_date"), "currency": v.get("currency"), "total": total, "tax": tax, "paid": paid,
                             "paid_date": v.get("paid_date"), "po_number": str(v.get("po_number") or "")[:100], "notes": str(v.get("notes") or "")[:2000], "lines": lines})
        out["sales"] = {"customers": customers, "invoices": invoices}
    bills_in = (mods.get("categorizer") or {}).get("bills") or []
    if bills_in:
        bills = []
        for i, b in enumerate(bills_in, 1):
            at = f"bill {i} ({str(b.get('vendor') or '')[:40]} {b.get('invoice_number') or ''})"
            if not cents_ok(b.get("amount"), True):
                bad(f"{at}: amount must be whole cents above 0")
            for k in ("bill_date", "due_date"):
                if b.get(k) and not iso(b.get(k)):
                    bad(f"{at}: {k} must be YYYY-MM-DD")
            if b.get("currency") not in ("CAD", "USD"):
                bad(f"{at}: currency must be CAD or USD")
            for k in ("account", "ap_account"):
                if b.get(k) and b[k] not in account_codes:
                    bad(f"{at}: {k} {b[k]!r} is not one of the accounts")
            bills.append({"vendor": str(b.get("vendor") or "").strip()[:200], "invoice_number": str(b.get("invoice_number") or "").strip()[:100], "bill_date": b.get("bill_date") or None,
                          "due_date": b.get("due_date") or None, "amount": b.get("amount"), "currency": b.get("currency"), "paid": bool(b.get("paid")),
                          "account": b.get("account") or None, "ap_account": b.get("ap_account") or None, "summary": str(b.get("summary") or "")[:1000]})
        out["categorizer"] = {"bills": bills}
    if problems:
        die("the books file's modules part has problems:\n  - " + "\n  - ".join(problems[:40]))
    return out


def qn(v):
    """A SQL literal, NULL for None."""
    return "NULL" if v is None else q(v)


def modules_sql(mods):
    """SQL that fills the modules' own tables (their schemas already exist)."""
    out = ["BEGIN;"]
    BY = q("quickbooks-import")
    s = mods.get("sales")
    if s:
        out.append("SET LOCAL search_path = mod_sales;")
        for c in s["customers"]:
            out.append(f"INSERT INTO customers (name, company, email, phone, address, tax_id, currency, terms_days, notes) VALUES ({q(c['name'])}, {q(c['company'])}, {q(c['email'])}, {q(c['phone'])}, {q(c['address'])}, {q(c['tax_id'])}, {q(c['currency'])}, {qn(c['terms_days']) if c['terms_days'] is None else c['terms_days']}, {q(c['notes'])});")
        for v in s["invoices"]:
            status = "paid" if v["paid"] >= v["total"] else "open"
            lines = ", ".join(f"({n}, {q(l['description'])}, {l['quantity']}::bigint, {l['unit_price']}::bigint, {l['amount']}::bigint)" for n, l in enumerate(v["lines"], 1))
            out.append(
                f"WITH d AS (INSERT INTO documents (kind, number, customer_id, status, issue_date, due_date, currency, po_number, notes, subtotal_cents, tax_cents, total_cents, paid_cents, issued_at, created_by)\n"
                f"  SELECT 'invoice', {q(v['number'])}, (SELECT id FROM customers WHERE lower(name) = lower({q(v['customer'])}) ORDER BY id LIMIT 1), {q(status)}, {q(v['issue_date'])}, {q(v['due_date'])}, {q(v['currency'])}, {q(v['po_number'])}, {q(v['notes'])},"
                f" {v['total'] - v['tax']}, {v['tax']}, {v['total']}, {v['paid']}, {q(v['issue_date'])}::date, {BY} RETURNING id),\n"
                f"l AS (INSERT INTO document_lines (document_id, position, description, quantity, unit_price_cents, amount_cents) SELECT d.id, x.n, x.d, x.q, x.p, x.a FROM d, (VALUES {lines}) AS x(n, d, q, p, a) RETURNING 1)\n"
                + (f"INSERT INTO payments (document_id, payment_date, amount_cents, method, reference, created_by) SELECT d.id, {q(v['paid_date'] or v['issue_date'])}, {v['paid']}, 'QuickBooks', {q('' if v['paid_date'] else 'payment date not in the QuickBooks export')}, {BY} FROM d;" if v["paid"] > 0 else "SELECT count(*) FROM l;")
            )
        # New invoices continue after the highest imported number.
        out.append("UPDATE settings SET next_invoice_number = greatest(next_invoice_number, 1 + coalesce((SELECT max((substring(number FROM '(\\d{1,9})$'))::bigint) FROM documents WHERE kind = 'invoice' AND number ~ '\\d$'), 0))::int;")
    b = mods.get("categorizer")
    if b:
        out.append("SET LOCAL search_path = mod_categorizer;")
        for x in b["bills"]:
            out.append(
                "INSERT INTO bills (kind, status, vendor, invoice_number, bill_date, due_date, amount_cents, currency, account_code, summary, source, ap_account, paid_at, updated_by) VALUES "
                f"('bill', {q('paid' if x['paid'] else 'open')}, {q(x['vendor'])}, {q(x['invoice_number'])}, {qn(x['bill_date'])}, {qn(x['due_date'])}, {x['amount']}, {q(x['currency'])}, {qn(x['account'])}, {q(x['summary'] or 'Imported from QuickBooks')}, 'upload', {qn(x['ap_account'])}, "
                f"{(qn(x['due_date'] or x['bill_date']) + '::date') if x['paid'] and (x['due_date'] or x['bill_date']) else 'NULL'}, {BY});"
            )
    out.append("COMMIT;")
    return "\n".join(out) + "\n"


def q(s):
    """A SQL string literal."""
    return "'" + str(s).replace("\x00", "").replace("'", "''") + "'"


def load_sql(accounts, entries, entities):
    out = ["BEGIN;"]
    for i in range(0, len(accounts), 200):
        rows = ",\n".join(f"({q(a['code'])}, {q(a['name'])}, {q(a['type'])}::account_type, {q(a['currency'])}, {q(a['description'])}, {'NULL' if a['kind'] is None else q(a['kind'])})" for a in accounts[i:i + 200])
        out.append(f"INSERT INTO accounts (code, name, type, currency, description, kind) VALUES\n{rows};")
    for i in range(0, len(entities), 200):
        rows = ",\n".join(f"({q(x['name'])}, {'true' if x['customer'] else 'false'}, {'true' if x['vendor'] else 'false'}, {q(x['email'])}, {q(x['phone'])}, {q(x['address'])}, {q(x['notes'])})" for x in entities[i:i + 200])
        out.append(f"INSERT INTO entities (name, is_customer, is_vendor, email, phone, address, notes) VALUES\n{rows};")
    for a in accounts:
        if a["parent"]:
            out.append(f"UPDATE accounts SET parent_id = (SELECT id FROM accounts WHERE code = {q(a['parent'])}) WHERE code = {q(a['code'])};")
    for e in entries:
        vals = ", ".join(f"({n}, {q(l['account'])}, {l['amount']}::bigint, {q(l['memo'])})" for n, l in enumerate(e["lines"], 1))
        out.append(
            f"WITH e AS (INSERT INTO journal_entries (entry_date, description, reference, entity_id) VALUES ({q(e['date'])}, {q(e['description'])}, {q(e['reference'])}, "
            + (f"(SELECT id FROM entities WHERE lower(name) = lower({q(e['entity'])}))" if e["entity"] else "NULL") + ") RETURNING id)\n"
            f"INSERT INTO transactions (journal_entry_id, account_id, currency, line_number, amount, memo)\n"
            f"SELECT e.id, a.id, a.currency, v.n, v.amount, v.memo FROM e, (VALUES {vals}) AS v(n, code, amount, memo) JOIN accounts a ON a.code = v.code ORDER BY v.n;"
        )
    out.append("COMMIT;")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------

def version_of(bindir):
    try:
        out = subprocess.run([str(Path(bindir) / "pg_dump"), "--version"], capture_output=True, text=True, timeout=20).stdout
        m = re.search(r"(\d+)(?:\.\d+)?", out)
        return int(m[1]) if m else None
    except (OSError, subprocess.SubprocessError):
        return None


def has_server(bindir):
    return all((Path(bindir) / b).exists() for b in ("initdb", "pg_ctl", "postgres", "psql", "pg_dump", "pg_restore"))


def find_postgres(want, allow_install, work):
    """A bin directory with PostgreSQL `want` (initdb, pg_ctl, psql, pg_dump)."""
    candidates = [os.environ.get("LEDGER_PG_BIN", ""), f"/usr/lib/postgresql/{want}/bin", f"/usr/pgsql-{want}/bin", f"/opt/homebrew/opt/postgresql@{want}/bin", f"/usr/local/opt/postgresql@{want}/bin"]
    on_path = shutil.which("pg_dump")
    if on_path:
        candidates.append(str(Path(on_path).resolve().parent))
    found_other = []
    for c in candidates:
        if c and has_server(c):
            v = version_of(c)
            if v == want:
                return Path(c)
            if v:
                found_other.append(f"{c} (PostgreSQL {v})")
    if allow_install:
        print(f"PostgreSQL {want} is not installed here; getting it from PyPI (postgresql-binaries)...")
        dl = work / "wheel"
        r = subprocess.run([sys.executable, "-m", "pip", "download", f"postgresql-binaries=={want}.*", "--no-deps", "--only-binary", ":all:", "-q", "-d", str(dl)], capture_output=True, text=True)
        wheels = list(dl.glob("*.whl")) if dl.exists() else []
        if r.returncode == 0 and wheels:
            import zipfile
            with zipfile.ZipFile(wheels[0]) as z:
                name = next((n for n in z.namelist() if n.endswith(".tar.gz")), None)
                if name:
                    z.extract(name, work / "pg")
                    with tarfile.open(work / "pg" / name) as tar:
                        try:
                            tar.extractall(work / "pg", filter="data")
                        except TypeError:  # Python < 3.12
                            tar.extractall(work / "pg")
                    for b in (work / "pg").rglob("bin"):
                        if has_server(b) and version_of(b) == want:
                            return b
        why = (r.stderr or r.stdout).strip().splitlines()[-1:] or ["no wheel for this platform"]
        print(f"  could not get it from PyPI: {why[0]}")
    die(
        f"PostgreSQL {want} is needed to write a dump Ledger can restore, and it isn't on this machine"
        + (f" (found: {', '.join(found_other)})" if found_other else "")
        + f".\nInstall PostgreSQL {want} (for example the postgresql-{want} package from apt.postgresql.org, or `brew install postgresql@{want}`) and run this again,"
        + " or set LEDGER_PG_BIN to its bin directory.\nIf Ledger's server runs a newer PostgreSQL, pass --pg-version with that number."
    )


class Cluster:
    """A throwaway PostgreSQL server in a temporary directory, reached through a Unix socket."""

    def __init__(self, bindir, work):
        self.bin, self.work = Path(bindir), Path(work)
        self.data, self.sock = self.work / "data", self.work / "sock"
        self.user = None
        if os.geteuid() == 0:
            # PostgreSQL refuses to run as root: use an unprivileged account.
            for name in ("postgres", "nobody", "daemon"):
                try:
                    self.user = pwd.getpwnam(name)
                    break
                except KeyError:
                    continue
            if not self.user:
                die("running as root and there is no unprivileged account (postgres, nobody) to run PostgreSQL as")

    def run(self, cmd, **kw):
        extra = {"user": self.user.pw_uid, "group": self.user.pw_gid} if self.user else {}
        env = {**os.environ, "PGHOST": str(self.sock), "PGPORT": "54329", "PGUSER": "ledger_build", "PGDATABASE": "postgres", "LC_ALL": "C", "HOME": str(self.work), "TZ": "UTC"}
        env.pop("PGPASSWORD", None)
        r = subprocess.run([str(self.bin / cmd[0]), *cmd[1:]], capture_output=True, text=True, env=env, cwd=str(self.work), **extra, **kw)
        if r.returncode != 0:
            tail = "\n".join((r.stderr or r.stdout).strip().splitlines()[-8:])
            raise RuntimeError(f"{cmd[0]} failed:\n{tail}")
        return r.stdout

    def start(self):
        self.sock.mkdir(parents=True, exist_ok=True)
        if self.user:
            for p in (self.work, self.sock):
                os.chown(p, self.user.pw_uid, self.user.pw_gid)
            os.chmod(self.work, 0o755)
        self.run(["initdb", "-D", str(self.data), "-U", "ledger_build", "-E", "UTF8", "--locale=C", "-A", "trust"])
        self.run(["pg_ctl", "-D", str(self.data), "-w", "-t", "60", "-l", str(self.work / "server.log"), "-o", f"-c listen_addresses='' -c unix_socket_directories='{self.sock}' -c port=54329 -c fsync=off -c timezone=UTC", "start"])

    def stop(self):
        try:
            self.run(["pg_ctl", "-D", str(self.data), "-m", "immediate", "-w", "stop"])
        except Exception:
            pass

    def psql(self, db, sql=None, file=None, capture=False):
        args = ["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-d", db] + (["-A", "-t"] if capture else [])
        if file:
            return self.run(args + ["-f", str(file)])
        return self.run(args, input=sql)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("books", help="books.json (from qb_convert.py, reviewed)")
    ap.add_argument("-o", "--output", default="ledger.dump")
    ap.add_argument("--pg-version", type=int, default=15, help="the PostgreSQL version Ledger's server runs (default 15, Debian 12)")
    ap.add_argument("--no-install", action="store_true", help="don't fetch PostgreSQL from PyPI when it isn't installed")
    ap.add_argument("--check", action="store_true", help="only check books.json and print the summary; build nothing")
    a = ap.parse_args()

    doc = json.load(open(a.books, encoding="utf-8"))
    accounts, entries, entities = check_books(doc)
    mods = check_modules(doc, {x["code"] for x in accounts})
    cents = lambda n: f"{n / 100:,.2f}"
    bal = {x["code"]: 0 for x in accounts}
    for e in entries:
        for l in e["lines"]:
            bal[l["account"]] += l["amount"]
    print(f"{a.books}: {len(accounts)} accounts, {len(entries)} entries" + (f", {min(e['date'] for e in entries)} to {max(e['date'] for e in entries)}" if entries else ""))
    if entities:
        print(f"{len(entities)} entities ({sum(1 for x in entities if x['customer'])} customers, {sum(1 for x in entities if x['vendor'])} vendors); {sum(1 for e in entries if e['entity'])} entries name one")
    subs = sum(1 for x in accounts if x["parent"])
    if subs:
        print(f"{subs} of the accounts are sub-accounts")
    print("closing balances by type (debits positive):")
    for t in TYPES:
        print(f"  {t:<10} {cents(sum(bal[x['code']] for x in accounts if x['type'] == t)):>16}")
    if "sales" in mods:
        inv = mods["sales"]["invoices"]
        print(f"Sales module: {len(mods['sales']['customers'])} customers, {len(inv)} invoices ({sum(1 for v in inv if v['paid'] < v['total'])} unpaid, {cents(sum(v['total'] - v['paid'] for v in inv))} outstanding)")
    if "categorizer" in mods:
        bl = mods["categorizer"]["bills"]
        print(f"Auto sort module: {len(bl)} bills ({sum(1 for x in bl if not x['paid'])} unpaid, {cents(sum(x['amount'] for x in bl if not x['paid']))} owing)")
    if a.check:
        print("books.json is consistent; nothing was built (--check)")
        return

    work = Path(tempfile.mkdtemp(prefix="ledger-dump-"))
    os.chmod(work, 0o755)
    cluster = None
    try:
        bindir = find_postgres(a.pg_version, not a.no_install, work)
        print(f"using PostgreSQL {a.pg_version} in {bindir}")
        cluster = Cluster(bindir, work)
        cluster.start()
        cluster.psql("postgres", "CREATE DATABASE ledger ENCODING 'UTF8' TEMPLATE template0;")
        # Ledger's schema as a fresh install has it: schema.sql, then each migration, recorded.
        cluster.psql("ledger", file=DB_DIR / "schema.sql")
        cluster.psql("ledger", "CREATE TABLE IF NOT EXISTS public.schema_migrations (name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now());")
        for m in sorted((DB_DIR / "migrations").glob("[0-9]*.sql")):
            cluster.psql("ledger", "BEGIN;\n" + m.read_text(encoding="utf-8") + f"\n;\nINSERT INTO public.schema_migrations (name) VALUES ({q(m.name)});\nCOMMIT;\n")
        sql = work / "load.sql"
        sql.write_text(load_sql(accounts, entries, entities), encoding="utf-8")
        os.chmod(sql, 0o644)
        cluster.psql("ledger", file=sql)
        if mods:
            # Each module's own schema, as Ledger's module installer leaves it: its
            # migrations run with the schema as search_path, and are recorded.
            cluster.psql("ledger", "CREATE SCHEMA ledger_modules; CREATE TABLE ledger_modules.migrations (module_id text NOT NULL, name text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (module_id, name));")
            for mid in mods:
                schema = MODULES[mid]
                cluster.psql("ledger", f"CREATE SCHEMA {schema};")
                for m in sorted((MODULES_DIR / mid / "migrations").glob("[0-9]*.sql")):
                    cluster.psql("ledger", f"BEGIN;\nSET LOCAL search_path = {schema};\n" + m.read_text(encoding="utf-8") + f"\n;\nINSERT INTO ledger_modules.migrations (module_id, name) VALUES ({q(mid)}, {q(m.name)});\nCOMMIT;\n")
            msql = work / "modules.sql"
            msql.write_text(modules_sql(mods), encoding="utf-8")
            os.chmod(msql, 0o644)
            cluster.psql("ledger", file=msql)
        n_acc, n_ent, n_lines, total = cluster.psql("ledger", "SELECT (SELECT count(*) FROM accounts), (SELECT count(*) FROM journal_entries), (SELECT count(*) FROM transactions), (SELECT coalesce(sum(amount), 0) FROM transactions);", capture=True).strip().split("|")
        if int(n_acc) != len(accounts) or int(n_ent) != len(entries) or int(total) != 0:
            die(f"the database holds {n_acc} accounts and {n_ent} entries (sum {total}), not what the books file has")
        tmp_dump = work / "ledger.dump"
        cluster.run(["pg_dump", "--format=custom", "--compress=6", "--no-owner", "--no-privileges", f"--file={tmp_dump}", "-d", "ledger"])
        listing = cluster.run(["pg_restore", "--list", str(tmp_dump)])
        if "TABLE DATA public journal_entries" not in listing:
            die("the dump did not come out right (pg_restore --list does not show the journal entries)")
        shutil.copyfile(tmp_dump, a.output)
        version = (DB_DIR / "LEDGER_VERSION").read_text().strip()
        print(f"\nwrote {a.output} ({os.path.getsize(a.output):,} bytes): {n_acc} accounts, {n_ent} entries, {n_lines} lines, all balanced")
        for mid in mods:
            print(f"includes the {'Sales' if mid == 'sales' else 'Auto sort'} module's data (module {mid} {(MODULES_DIR / mid / 'MODULE_VERSION').read_text().strip()} or later must be installed in Ledger)")
        print(f"made with PostgreSQL {a.pg_version} and Ledger {version}'s schema: restore it in Ledger {version} or later")
    except RuntimeError as e:
        die(str(e))
    finally:
        if cluster:
            cluster.stop()
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
