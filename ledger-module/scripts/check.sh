#!/bin/sh
# Runs Ledger's module checker on a module folder: validates the manifest the
# way Ledger does, then (with TEST_DATABASE_URL) loads the module into a real
# Ledger on a scratch database and calls its routes.
#
#   sh <this skill>/scripts/check.sh [module-dir] [--serve 8098]
#
# module-dir defaults to the current directory. Needs a Ledger checkout:
# $LEDGER_DIR, a sibling of the module (../Accounting, ../Bookeeping,
# ../ledger), or it shallow-clones mastifdogo/Bookeeping.
set -eu
case "${1:-}" in
	"" | --*) module=$(pwd) ;;
	*) module=$(cd "$1" && pwd); shift ;;
esac
[ -f "$module/ledger-module.json" ] || { echo "$module has no ledger-module.json" >&2; exit 2; }
checker=.claude/skills/ledger-module/scripts/check-module.ts
ledger=${LEDGER_DIR:-}
if [ -z "$ledger" ]; then
	for d in "$module/../Accounting" "$module/../Bookeeping" "$module/../ledger" "${TMPDIR:-/tmp}/ledger-for-modules"; do
		if [ -f "$d/$checker" ]; then
			ledger=$(cd "$d" && pwd)
			break
		fi
	done
fi
if [ -z "$ledger" ]; then
	ledger="${TMPDIR:-/tmp}/ledger-for-modules"
	echo "Cloning Ledger into $ledger (set LEDGER_DIR to use another checkout)" >&2
	git clone --quiet --depth 1 https://github.com/mastifdogo/Bookeeping "$ledger"
fi
[ -f "$ledger/$checker" ] || { echo "$ledger has no $checker; update that Ledger checkout" >&2; exit 2; }
[ -d "$ledger/backend/node_modules" ] || (cd "$ledger/backend" && npm ci --silent)
exec node "$ledger/$checker" "$module" "$@"
