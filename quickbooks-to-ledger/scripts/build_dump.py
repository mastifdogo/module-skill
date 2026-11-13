#!/usr/bin/env python3
"""Builds a Ledger database dump (ledger.dump) from a books.json.

  python3 build_dump.py books.json -o ledger.dump

The dump is what Ledger's backups contain: upload it under Settings ->
Backups -> Restore from a backup -> "upload a dump file" (Ledger 0.14.2 or
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
        accounts.append({"code": code, "name": name[:200], "type": a.get("type"), "currency": a.get("currency"), "description": str(a.get("description") or "").strip()[:1000]})
    if not accounts:
        die("the books file has no accounts")
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
        entries.append({"date": d, "description": desc, "reference": str(e.get("reference") or "").strip()[:100], "lines": lines})
        if len(problems) >= 40:
            break
    if problems:
        die("the books file has problems:\n  - " + "\n  - ".join(problems) + ("\n  ..." if len(problems) >= 40 else ""))
    return accounts, entries


def q(s):
    """A SQL string literal."""
    return "'" + str(s).replace("\x00", "").replace("'", "''") + "'"


def load_sql(accounts, entries):
    out = ["BEGIN;"]
    for i in range(0, len(accounts), 200):
        rows = ",\n".join(f"({q(a['code'])}, {q(a['name'])}, {q(a['type'])}::account_type, {q(a['currency'])}, {q(a['description'])})" for a in accounts[i:i + 200])
        out.append(f"INSERT INTO accounts (code, name, type, currency, description) VALUES\n{rows};")
    for e in entries:
        vals = ", ".join(f"({n}, {q(l['account'])}, {l['amount']}::bigint, {q(l['memo'])})" for n, l in enumerate(e["lines"], 1))
        out.append(
            f"WITH e AS (INSERT INTO journal_entries (entry_date, description, reference) VALUES ({q(e['date'])}, {q(e['description'])}, {q(e['reference'])}) RETURNING id)\n"
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

    accounts, entries = check_books(json.load(open(a.books, encoding="utf-8")))
    cents = lambda n: f"{n / 100:,.2f}"
    bal = {x["code"]: 0 for x in accounts}
    for e in entries:
        for l in e["lines"]:
            bal[l["account"]] += l["amount"]
    print(f"{a.books}: {len(accounts)} accounts, {len(entries)} entries" + (f", {min(e['date'] for e in entries)} to {max(e['date'] for e in entries)}" if entries else ""))
    print("closing balances by type (debits positive):")
    for t in TYPES:
        print(f"  {t:<10} {cents(sum(bal[x['code']] for x in accounts if x['type'] == t)):>16}")
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
        sql.write_text(load_sql(accounts, entries), encoding="utf-8")
        os.chmod(sql, 0o644)
        cluster.psql("ledger", file=sql)
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
        print(f"made with PostgreSQL {a.pg_version} and Ledger {version}'s schema: restore it in Ledger {version} or later")
    except RuntimeError as e:
        die(str(e))
    finally:
        if cluster:
            cluster.stop()
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
