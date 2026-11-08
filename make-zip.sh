#!/bin/sh
# Rebuilds ledger-module-skill.zip (the skill folder at the zip's top level,
# as Claude's skill upload expects). Run after changing ledger-module/.
set -eu
cd "$(dirname "$0")"
rm -f ledger-module-skill.zip
if command -v zip >/dev/null 2>&1; then
	zip -qrX ledger-module-skill.zip ledger-module
else
	python3 -c "import shutil; shutil.make_archive('ledger-module-skill', 'zip', '.', 'ledger-module')"
fi
echo "wrote ledger-module-skill.zip"
