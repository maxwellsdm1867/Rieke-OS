#!/bin/sh
set -eu
application="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ ! -x "$application/.rieke-runtime/venv/bin/python" ]; then
  echo 'Run ./install.sh first.' >&2; exit 1
fi
export PATH="$application/.rieke-runtime/native/bin:$PATH"
exec "$application/.rieke-runtime/venv/bin/python" "$application/rieke.py" launch "$@"
