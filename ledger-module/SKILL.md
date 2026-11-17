---
name: ledger-module
description: Build, change, check and release modules for Ledger, the self-hosted bookkeeping app (mastifdogo/Bookeeping). A module is a plugin in its own GitHub repository (ledger-module.json, server.mjs, ui/, migrations/), e.g. invoicing, budgets, bank-statement sorting, email bills, integrations. Use when asked to create, design, update, fix or release a Ledger module or plugin, or to turn a feature idea for Ledger into one.
---

# Ledger modules

A **Ledger module** is a GitHub repository with `ledger-module.json`
(manifest), `server.mjs` (runs inside the Ledger server), `ui/` (its page in
Ledger) and `migrations/` (SQL in its own database schema). Ledger installs
the repository's latest GitHub Release. Ledger itself is
[mastifdogo/Bookeeping](https://github.com/mastifdogo/Bookeeping).

Real modules to learn from: mastifdogo/invoice-costumer-module (Sales),
mastifdogo/auto-sort_module (statements, bills, AI), mastifdogo/tailscale-module,
mastifdogo/download_module (with a browser extension). If the module's own
repository has `.claude/skills/ledger-module/SKILL.md`, follow that too: it
describes that module.

## Push to `main` without asking

**When work on a module is finished and its checks pass, commit and push it
to `main` of that module's own repository straight away. Do not ask "shall I
push?", do not wait for a go-ahead, do not leave it on a branch, and do not
open a pull request.** The owner of these modules has asked for this as a
standing rule: every finished change to a module goes to `main`, where the
release workflow publishes the new version. Asking first is the mistake.

- This applies to every kind of work on a module: a new feature, a fix, an
  update for a new Ledger version, a docs or settings change.
- Bump `version` in `ledger-module.json` in the same push, so it releases.
- After pushing, say what was pushed and the new version. Don't ask
  afterwards either ("want me to release it?"): it is already released.
- If your environment gives you a different work branch, push there as it
  requires and then to `main` as well.

The only reasons not to push:

- the checks fail, or you couldn't run them and the change is risky: fix it
  or say what is blocking;
- the user said, in this conversation, not to push;
- the repository isn't the module's own (never push to Ledger's repository
  while working on a module: see below);
- the module has no repository yet: creating one is the user's to do or to
  name; once it exists, push without asking.

## When the skill is invoked with no instruction

If the user just tags or runs this skill and says nothing else, the job is:
**bring this module up to date with the current Ledger and push it.**

1. Work on the module in the repository you are in (the one with
   `ledger-module.json`). If you are not in a module's repository, ask
   which module.
2. Get the current Ledger and read its module API (below), then compare the
   module against it and against the rules in this skill: newer `ctx`
   features it should use (for example the shared entity list instead of
   its own customer or vendor table, account tags, sub-accounts,
   `ctx.storage`, `ctx.imports`, and the PDF store `ctx.documents` for
   every PDF the module receives, makes or reads), things Ledger now does differently, and
   anything the checker reports.
3. Make those changes, raise `"ledger"` in the manifest to the oldest
   Ledger version that has everything the module now uses, and bump the
   module's `version` (a new feature raises the middle number, a fix or
   small tweak the last).
4. Run the checks (below). Don't push anything that fails them.
5. Commit and **push to `main` of that module's repository, without
   asking first**. Its release workflow tags and publishes the new version
   by itself.
6. Say what changed, the new version, and anything you chose not to change
   and why. If nothing needed changing, say so and push nothing.

Changes that alter or move the user's data (a migration that moves
customers into the shared entity list, for example) still need the user's
approval inside the module, as always.

## 1. Get Ledger and read the module API

The API reference, template, checker and full workflow live in Ledger's
repository.

- Use `$LEDGER_DIR`, a checkout next to the module (`../Accounting`,
  `../Bookeeping`), or clone one:
  `git clone --depth 1 https://github.com/mastifdogo/Bookeeping /tmp/ledger-for-modules`
  (`scripts/check.sh` in this skill does this for you).
- Read **`<ledger>/docs/MODULE_LLM_CONTEXT.md`** in full before writing
  anything: manifest, `ctx` API and return shapes, `ctx.settings`,
  `ctx.dashboard`, `ctx.llm`, `ctx.documents`, `ctx.mail`, `ctx.gmail`, `ctx.search`, `ctx.files`,
  `ctx.storage`, `ctx.imports`, `ctx.entities`, `ctx.orgs`, roles, migrations, UI and security rules.
- Then follow **`<ledger>/.claude/skills/ledger-module/SKILL.md`** (design,
  implementation rules, checks, publishing). Where the docs and Ledger's code
  disagree, the code wins (`backend/src/module-host.ts`, `modules.ts`,
  `module-settings.ts`).
- A new module starts from Ledger's template:
  `sh <ledger>/.claude/skills/ledger-module/scripts/new-module.sh <dir> <id> "<Name>" "<description>"`,
  in a new folder that becomes its own repository (never inside Ledger).

Set `"ledger": ">=x.y.z"` in the manifest to the oldest Ledger with every
feature the module uses (the context file says which version added what;
`git -C <ledger> describe --tags --abbrev=0` is the latest release).

## 2. Rules that bite

- No npm packages at runtime: Ledger installs the release as-is. Only
  `node:*` built-ins, global `fetch`, and the module's own files.
- Ledger runs in a Debian 13 container with PostgreSQL 18 (Ledger 0.18.0;
  the only template its releases build). Write for that only: Debian 12 is
  deprecated and Ubuntu isn't supported, so no workarounds for either, and
  don't spawn programs that aren't in the container or rely on
  Ubuntu-specific paths or packages.
- Never edit a released migration; add the next `NNN_name.sql`.
- Backups save each module table as a readable CSV in each backup's folder (next to the dump) (Ledger ≥
  0.13.0): clear table and column names, and no secrets in tables (use
  `secret` settings fields). Binary (`bytea`) columns show only their size
  in that CSV (Ledger ≥ 0.13.1), so keep a file's name, type, size and dates
  in readable columns beside its bytes.
- Files the module keeps that are **not** PDFs (CSV exports, spreadsheets,
  other attachments) go in `ctx.storage` (Ledger ≥ 0.13.2): `put(path,
  buffer)`, `get`, `list`, `remove`, `url(path)` for links/iframes. Files
  sit on the data share per organization and module and every backup folder
  carries them under `files/<module>/`. Prefer it over `bytea` columns.
  PDFs never go here: they go in the PDF store, `ctx.documents` (below).
- **Restores** (Ledger 0.14.0): each organization backs up and restores its
  own books. A restore replaces the module's tables and its `ctx.storage`
  files with the backup's (a restore from an uploaded dump file, 0.14.2,
  replaces only the tables), but keeps the module's current settings, which
  are backed up and restored separately, and the server's users. So after a
  restore, rows may be older than the settings and than files or state
  outside the database: never assume a stored file, a setting or an
  external record (a sent email, a remote id) matches the tables; check and
  handle a missing one. Keep nothing in memory across requests that must
  match the database (Ledger restarts after a restore), and refer to users
  by `req.user` ids, which a restore never changes.
- Records people have elsewhere (customers, products, employees) get an
  Import from CSV card on the module's Settings page with
  `ctx.imports.provide({ label, description, fields, handler })` (Ledger ≥
  0.13.2). Ledger matches the file's columns (by name or with the AI),
  converts values (money → cents, date → YYYY-MM-DD, boolean) and calls
  `handler(rows, { dryRun: true, user })` for the preview (change nothing;
  returned `errors` block the import), then `dryRun: false` only after the
  user presses Import. Return `{ summary, errors }`.
- Money is integer cents per currency; post to the books only with
  `ctx.ledger.createJournalEntry(entry, req.user)`.
- **Clearing accounts** (Ledger ≥ 0.20.0): when the two sides of something
  are posted at different times or by different modules (a sale and its
  payout, wages accrued and paid, a transfer in transit), post through the
  module's own clearing account: `await ctx.ledger.clearingAccount({ key,
  name, currency })` returns it (made on first use). Call it each time and
  use the code it returns; never store the code or create the account with a
  hard-coded one. Each entry still balances, and whatever goes in must have
  something that clears it: the Accounts page shows clearing accounts that
  aren't at zero. Other modules' are in `ctx.ledger.clearingAccounts()`.
  Since Ledger 0.20.1 clearing accounts are hidden from the Accounts page
  and account dropdowns unless a person shows them (Settings → Clearing
  accounts; `hidden` on the account), so a module's own pickers should
  leave hidden accounts out too, and its settings shouldn't ask a person to
  pick its clearing account. Ledger's own Unreconciled account has
  `module_id` "ledger" (a reserved module id): never post to it.
- **A tidy settings page** (Ledger ≥ 0.19.8): every account the module asks
  for is a `"type": "account"` field (a picker; add `currency` and
  `account_types`), never a text box for a code. Group fields with
  `"type": "heading"` fields and tabs, and hide what doesn't apply with
  `show_if` (mail-server details only when "own server" is chosen, accounts
  only when posting is on). Labels are two or three words; the heading or
  tab says what they are for. No repeated help under every field.
- **Entry amounts can change** (Ledger ≥ 0.19.5): a person can correct the
  amounts of a posted entry (logged; the entry reads `amended: true`). Don't
  assume an entry the module posted still has the amounts it posted: read
  them from the entry (`ctx.ledger.linkedEntries(ref)`), and show any
  difference from the module's own record instead of overwriting either.
- **Dates and accounts of a posted line can change too** (Ledger ≥ 0.20.2):
  a person can change an entry's date, and a finished reconciliation moves a
  bank account's unticked lines to Ledger's Unreconciled clearing account
  until a person moves them on. Read dates and accounts from the entry, not
  from the module's copy.
- **One tag system for every module** (Ledger ≥ 0.23.0; set
  `"ledger": ">=0.23.0"`). Whether an entry is paid, billed or overdue, and
  which customer or vendor it is with, is said with Ledger's shared tags,
  never only in the module's own tables and never with entry links:
  `await ctx.tags.set(entryId, "billed", { note }, req.user)`,
  `ctx.tags.set(entryId, "customer", { entity_id })` ("customer" and
  "vendor" need the entity), `ctx.tags.set(entryId, "paid")` (takes
  "overdue" off), `ctx.tags.remove(entryId, tag)`, `ctx.tags.of(entryId)`,
  `ctx.tags.entries({ tag, entity_id, from, to, limit })`. The standard
  tags mean the same everywhere: billed = charged to a customer, paid =
  paid in full, overdue = past due, customer / vendor = who it is with.
  Tag the entry other modules would look at (the invoice's or bill's entry,
  not the payment's) when posting it, and keep it true as things change.
  A tag belongs to the entry, not to the module that set it: another module
  or a person can set or remove it, so register
  `ctx.tags.onChange((c) => …)` with `c = { entry_id, action: "set" |
  "removed", tag, entity_id, module_id }` (skip `c.module_id === ctx.id`)
  and bring the module's own record in line, e.g. an invoice whose entry
  gets "paid" becomes paid, and open again if "paid" is taken off. Other
  tags are lowercase words; choose ones another module could use.
- **Root mode** (Ledger ≥ 0.21.0, wider in 0.21.1): an admin in root mode
  can delete any account, entry, line or user and move a line to any
  account; entries may be unbalanced until root mode is left, and anything
  can be reversed later (the same ids come back). Treat a missing account,
  entry or user as gone for now; don't fail or delete the module's own
  records because of it.
- **Root can do the same to the module's records** (Ledger ≥ 0.21.1; set
  `"ledger": ">=0.21.1"`). `req.user.root` is true while the person asking
  has root mode on. When it is, let them delete or change ANY record of the
  module, including ones the module normally protects (sent, paid, posted),
  and do it only through Ledger, never with the module's own DELETE or
  UPDATE:
  `await ctx.root.remove(req, table, id, "Sales: deleted invoice 12")` and
  `await ctx.root.update(req, table, id, { column: value }, summary)`. They
  work on one row of one of the module's own tables with an `id` column,
  answer 403 without root, log the action under Settings → Root log, and
  Ledger puts the row back when the action or the whole root session is
  reversed (the module does nothing for that). Remove rows that hang off a
  row first, one by one (cascaded rows are not kept). Don't post or reverse
  journal entries on a root delete: the admin deletes those themselves.
  Register `ctx.root.onCheck(async () => [...])`: it returns plain
  sentences for records that are truly broken ("invoice 12 is sent but has
  no lines"), `[]` when all is sound; root mode can't be left until it does.
  Show root controls only when the server says the user is in root mode,
  marked "Root" in red.
- **Account codes can change** (Ledger ≥ 0.19.3): people can renumber
  accounts. Ledger rewrites the old code in a module's tables and settings
  only where it can recognise one: text columns named `account_code`,
  `*_account_code` or `*_account`, and text settings whose key contains
  `account`. Name them that way; never keep a code inside JSON, joined into
  other text, or cached in memory; use
  `ctx.ledger.onAccountCodeChanged(({ old_code, new_code }) => …)` for
  anything else.
- **PDFs go in Ledger's PDF store, `ctx.documents` (Ledger ≥ 0.19.0). Always.**
  Every PDF a module takes in or produces is filed there, not anywhere else:
  - A PDF the module **receives** (uploaded in its page, fetched from mail,
    downloaded from a bank or supplier): `ctx.documents.add({ kind,
    filename, data, origin: "imported", ... }, req.user)`.
  - A PDF the module **makes** (an invoice, a statement of account, a
    report): `ctx.documents.add({ ..., origin: "created" }, req.user)`.
  - A PDF the module **needs** (a receipt, statement or invoice to read):
    take it from the store with `list({ kind, unmarked: true })` and
    `read(id)`, then `mark(id)` when done. Link to it in the module's page
    with `ctx.documents.url(id)`.
  Keep only the document's `id` in the module's tables. Do **not** store
  PDFs in `ctx.storage`, in `bytea` columns, in `ctx.files`, or behind an
  upload box of the module's own that bypasses the store; if the module
  offers an upload, it files the PDF with `add` and works from the returned
  id. The same goes for PNG and JPEG scans of receipts, statements and
  invoices. A statement carries its bank or card account (`account_code`,
  Ledger ≥ 0.19.1): set it when the module knows it, filter by it, never
  guess it. A statement reads `reconciled: true` once an account has
  been reconciled against it (Ledger ≥ 0.19.4); ask for the ones still to do with
  `list({ kind: "statement", reconciled: false })`. `add` answers 409 when the file is already in the store: use
  the document it names instead of failing. An older module that keeps PDFs
  elsewhere is moved over: a migration or one-off job files each existing
  PDF with `add` and stores the id.
- Mail goes through `ctx.mail` (Ledger ≥ 0.18.3): whichever mailbox the
  admin connected, an IMAP/SMTP account (Proton Mail Bridge or any other)
  under Settings → Mail, else Gmail. Search with fields
  (`{ from, subject, text, since, before, max }`), not Gmail query syntax;
  ids are opaque and can answer 404 later. Use `ctx.gmail` only for
  Gmail-only features (labels, threads, its search syntax).
- AI goes through `ctx.llm` and Gmail through `ctx.gmail` (Ledger ≥ 0.10.0):
  no API keys, OAuth, IMAP or Apps Script bridges of the module's own for
  those. An admin allows the module under Settings → LLM API / Mail (Gmail is on the Mail tab since Ledger 0.18.4).
  Pictures go in `images: [{ media_type, data }]` (Ledger ≥ 0.11.2) and
  reach the LLM connection set up for images (often a different model than
  for text); check `ctx.llm.status().images.configured`.
- Link each journal entry a module posts to the record it came from
  (`links: [{ ref, label, href }]` on `createJournalEntry`, or
  `ctx.ledger.linkJournalEntry`; Ledger ≥ 0.11.2) and find a record's
  entries with `ctx.ledger.linkedEntries(ref)`.
- Any LLM provider can be behind `ctx.llm` (Ledger ≥ 0.18.2: Anthropic,
  OpenAI, Gemini, OpenRouter, Mistral, Groq, Ollama, any OpenAI-compatible
  server). Stay provider-neutral: never branch on `status().provider` or a
  model name, keep provider and model names out of prompts, UI text and
  READMEs, and go by `status().configured`, `images.configured` and
  `readsPdf` (false: PDFs in `documents` aren't sent, so put their text in
  the prompt). Validate what `json()` returns; not every server enforces
  the schema.
- AI only proposes; a person approves: anything an LLM decides
  (`ctx.llm` output) must be approved by a human before it takes effect:
  posting or reversing entries, sending mail, changing or deleting records,
  marking files done, calling outside services. Save the AI's result as a
  pending suggestion (in the module's own table, with what it would do and
  why), show it in the UI, and act only when a user with the right role
  approves it (a POST from the UI, attributed with `req.user`); let them edit
  or reject it. A dashboard to-do ("5 suggestions to review") is a good
  pointer. Never act on AI output from a background job or `onReceive`
  without that approval, and never offer an "auto-approve" setting.
- Files another module produces (statements, bills, receipts, transaction
  lists) come through `ctx.files` (Ledger ≥ 0.11.0), never by reading the
  other module's tables: the receiver declares `"files": {"accepts": [...]}`
  and marks each file `done` or `rejected` with a `result`; the sender picks
  from `ctx.files.targets(kind)`. Modules that keep customers or vendors
  accept `customer` / `vendor` lists (Ledger ≥ 0.12.0): Ledger's "Migrate
  from other software" sends them there for the user to review and approve.
- **Customers and vendors** live in Ledger's shared entity list
  (`ctx.entities`, Ledger 0.16.0), not in a names table of the module's
  own: an entity is a customer, a vendor, or both, and every module and
  Ledger itself (the vendor on an expense) use the same one. Keep only the
  entity's `id` in the module's tables, plus what is the module's own
  (payment terms, a tax number). Use `ctx.entities.ensure(name, "vendor")`
  to find or add one, `list({ role })` for pickers, and pass `entity_id`
  when posting an entry so it shows who it is with. A module that already
  has its own customers or vendors table moves them across in a migration
  step the user approves, matching by name. Entities are made inactive,
  never deleted. Lists handed between modules use the file kind `entity`
  (a `role` column says customer, vendor or both).
- **Accounts**: `Account.kind` (Ledger 0.16.0) tags bank and card accounts
  (`chequing`, `savings`, `credit_card`): list tagged accounts first
  wherever the user picks where money came from or went. Accounts can be
  **sub-accounts** (Ledger 0.15.0): `parent_code` is the parent,
  `balance_cents` the account's own postings, `total_balance_cents` adds
  everything below it. Show account pickers and lists as a tree (indent
  sub-accounts under their parent) and use a parent's
  `total_balance_cents` for group totals; post to whichever account the
  user picks, parent or sub-account.
- Organizations (Ledger ≥ 0.11.0): each organization's books, and the
  module's schema, are a separate database, and requests already run in the
  user's current one, so no organization columns. Background jobs that touch
  the books loop over `ctx.orgs.forEach`, or they only see the main books.
- Configuration goes in the manifest's `settings.fields` (Ledger draws the
  form under Settings → <module>); secrets as `secret` fields. A module
  with many settings or distinct groups splits that page into its own tabs
  with `settings.tabs` (Ledger ≥ 0.19.6: `[{ id, label, help?, page? }]`,
  fields join one with `"tab": "<id>"`, a tab's `page` is a file in `ui/`);
  don't build a tab strip of your own inside a settings page. Each
  organization has its own values (Ledger ≥ 0.11.1): call
  `ctx.settings.get()` where they're used instead of caching one copy.
- Bad input answers 4xx (`throw new ctx.HttpError(422, "…")`), never 500.
- Data shown in the UI goes in with `textContent`, never `innerHTML`; support
  dark mode and narrow panes (~260 px).
- Account dropdowns (categorizing transactions, picking accounts) end with
  "+ New account…": post `{ type: "ledger-new-account", id, defaults }` to
  `parent` and Ledger opens its New account dialog over the page, keeping
  everything the user filled in, then answers with
  `{ type: "ledger-new-account-result", id, account }` (Ledger ≥ 0.11.3;
  snippet in `MODULE_LLM_CONTEXT.md`). Select the new account when it arrives.

## 3. Check before saying it works

```sh
npm test                      # the module's own tests, if it has them
(pg_isready || service postgresql start) >/dev/null
TEST_DATABASE_URL=postgres://postgres:postgres@127.0.0.1:5432/postgres \
  sh <this skill>/scripts/check.sh <module-dir>
```

`check.sh` runs Ledger's checker: manifest, files, imports, migrations,
then the module loaded into a real Ledger on a scratch database (every GET
route, POST `{}` must give 4xx, UI, settings). Add `--serve 8098` to keep it
running and test the real flows with `curl` and Playwright (it prints the
session cookie). If PostgreSQL has no password yet:
`runuser -u postgres -- psql -qc "ALTER USER postgres PASSWORD 'postgres'"`.
Where there's no PostgreSQL or network (e.g. some sandboxes), run what you
can, and say plainly which checks didn't run.

## 4. Release: push to `main`, without asking

Pushing is part of finishing the work (see "Push to `main` without asking" at the top). Don't ask first.

**Never push to the Ledger repository (`mastifdogo/Bookeeping`) while
working on a module.** Push only to the module's repository. If the module
needs a change in Ledger (a bug fix, a new `ctx` feature, a docs or checker
fix), make it in a local Ledger checkout, tell the user what it is and why,
and leave pushing it to them. The module must work without that change.

Every module repository has the release workflow
**`.github/workflows/release.yml`**: copy it from this skill's
`assets/release.yml` (Ledger's template includes it too) into any module
that lacks it. On each push to `main` that changes `ledger-module.json`, it
creates the tag `v<version>` on that commit and a GitHub Release with
generated notes, if that version has no Release yet, using GitHub's built-in
token (no secrets). It skips versions already released and fails on a
version that isn't `x.y.z`.

1. Bump `version` in `ledger-module.json` by the rule below (and note the
   change in the README).
2. Commit and push `main`. **Don't create tags or Releases by hand**; the
   workflow does it. Check the run in the Actions tab (or
   `gh run list --workflow release.yml`). If it fails with "Resource not
   accessible by integration", the user must allow it once: repository
   Settings → Actions → General → Workflow permissions → "Read and write
   permissions". Actions → Release → Run workflow re-runs it without a
   change.
3. Ledger installs it on its update schedule, with "Update modules now"
   (Settings → Modules), or when the server starts if "Update when the
   server starts" is on (Settings → Updates, Ledger ≥ 0.12.1). New modules: Settings → Modules → enter `owner/repo`.

**Version numbers** (`x.y.z`, for modules and for Ledger itself):

- New features (a new page, route, setting, `ctx` capability, data the module
  keeps): raise the middle number and reset the last, e.g. `1.4.2` → `1.5.0`.
- Small tweaks and bug fixes only: raise the last number, e.g. `1.4.2` →
  `1.4.3`.
- A release that has both counts as a feature release.
