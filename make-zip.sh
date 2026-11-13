#!/bin/sh
# Rebuilds each skill's zip (the skill folder at the zip's top level, as
# Claude's skill upload expects). Run after changing a skill's folder.
set -eu
cd "$(dirname "$0")"
for skill in ledger-module quickbooks-to-ledger; do
	rm -f "$skill-skill.zip"
	if command -v zip >/dev/null 2>&1; then
		zip -qrX "$skill-skill.zip" "$skill" -x '*/__pycache__/*' '*.pyc'
	else
		python3 -c "import shutil, sys; shutil.make_archive(sys.argv[1] + '-skill', 'zip', '.', sys.argv[1])" "$skill"
	fi
	echo "wrote $skill-skill.zip"
done
