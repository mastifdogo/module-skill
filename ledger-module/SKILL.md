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

## 1. Get Ledger and read the module API

The API reference, template, checker and full workflow live in Ledger's
repository.

- Use `$LEDGER_DIR`, a checkout next to the module (`../Accounting`,
  `../Bookeeping`), or clone one:
  `git clone --depth 1 https://github.com/mastifdogo/Bookeeping /tmp/ledger-for-modules`
  (`scripts/check.sh` in this skill does this for you).
- Read **`<ledger>/docs/MODULE_LLM_CONTEXT.md`** in full before writing
  anything: manifest, `ctx` API and return shapes, `ctx.settings`,
  `ctx.dashboard`, `ctx.llm`, `ctx.gmail`, `ctx.search`, `ctx.files`,
  `ctx.orgs`, roles, migrations, UI and security rules.
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
- Ledger runs in a Debian 12 container (the only template its releases
  build; no Ubuntu): don't spawn programs that aren't in it or rely on
  Ubuntu-specific paths or packages.
- Never edit a released migration; add the next `NNN_name.sql`.
- Backups save each module table as a readable CSV in each backup's folder (next to the dump) (Ledger ≥
  0.13.0): clear table and column names, and no secrets in tables (use
  `secret` settings fields). Binary (`bytea`) columns show only their size
  in that CSV (Ledger ≥ 0.13.1), so keep a file's name, type, size and dates
  in readable columns beside its bytes.
- Money is integer cents per currency; post to the books only with
  `ctx.ledger.createJournalEntry(entry, req.user)`.
- AI goes through `ctx.llm` and Gmail through `ctx.gmail` (Ledger ≥ 0.10.0):
  no API keys, OAuth, IMAP or Apps Script bridges of the module's own for
  those. An admin allows the module under Settings → LLM API / Gmail.
  Pictures go in `images: [{ media_type, data }]` (Ledger ≥ 0.11.2) and
  reach the LLM connection set up for images (often a different model than
  for text); check `ctx.llm.status().images.configured`.
- Link each journal entry a module posts to the record it came from
  (`links: [{ ref, label, href }]` on `createJournalEntry`, or
  `ctx.ledger.linkJournalEntry`; Ledger ≥ 0.11.2) and find a record's
  entries with `ctx.ledger.linkedEntries(ref)`.
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
- Organizations (Ledger ≥ 0.11.0): each organization's books, and the
  module's schema, are a separate database, and requests already run in the
  user's current one, so no organization columns. Background jobs that touch
  the books loop over `ctx.orgs.forEach`, or they only see the main books.
- Configuration goes in the manifest's `settings.fields` (Ledger draws the
  form under Settings → <module>); secrets as `secret` fields. Each
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

## 4. Release (only when the user asks)

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
