# Ledger skills

Two [Claude](https://claude.ai) skills for [Ledger](https://github.com/mastifdogo/Bookeeping), the self-hosted bookkeeping app:

- **ledger-module**: build, change, check and release Ledger modules (below).
- **quickbooks-to-ledger**: upload a QuickBooks export to a chat (a Journal report as CSV/Excel, an Account List, or a Desktop .IIF file) and get back a `ledger.dump` to restore under Settings → Backups → Restore → upload a dump file. Upload [`quickbooks-to-ledger-skill.zip`](quickbooks-to-ledger-skill.zip) the same way as the other skill. Writing the dump needs PostgreSQL 15 where Claude runs its code (the skill looks for it and otherwise fetches it from PyPI); Ledger 0.16.0 or later restores it. QuickBooks sub-accounts come across as Ledger sub-accounts.

## ledger-module skill

A [Claude](https://claude.ai) skill for building, changing, checking and
releasing modules for [Ledger](https://github.com/mastifdogo/Bookeeping), the
self-hosted bookkeeping app. It works anywhere: it fetches Ledger itself for
the module API reference, the template and the checker.

```
ledger-module/
  SKILL.md           what Claude follows
  scripts/check.sh   runs Ledger's module checker on a module folder
  assets/release.yml the GitHub Actions workflow every module repo carries:
                     pushing a new version to main tags and releases it
ledger-module-skill.zip   the same folder, ready to upload
```

## Install

**Claude (claude.ai, desktop and mobile apps):** Settings → Capabilities:
turn on code execution, then under **Skills** upload
[`ledger-module-skill.zip`](ledger-module-skill.zip). (Menu names may differ
slightly between app versions.)

**Claude Code on your computer:** copy the folder into your personal skills:

```sh
git clone https://github.com/mastifdogo/module-skill
mkdir -p ~/.claude/skills && cp -R module-skill/ledger-module ~/.claude/skills/
```

Then ask for something like "build a Ledger module that tracks mileage" or
"add a setting to my Sales module". Module repositories that carry their own
`.claude/skills/ledger-module/` skill add notes about that module.

## Checking a module by hand

```sh
TEST_DATABASE_URL=postgres://postgres:postgres@127.0.0.1:5432/postgres \
  sh ledger-module/scripts/check.sh path/to/module
```

Without `TEST_DATABASE_URL` it checks the manifest, files, imports and
migrations only. With it, it also loads the module into a real Ledger on a
scratch database and calls its routes. It uses `$LEDGER_DIR`, a Ledger
checkout next to the module, or clones `mastifdogo/Bookeeping`.

## Changing the skill

Edit `ledger-module/`, run `sh make-zip.sh`, and commit both. Keep it in line
with the skill in Ledger's repository
(`.claude/skills/ledger-module/SKILL.md`) and the module repositories'
copies.
