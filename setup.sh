#!/bin/sh
set -eu
TOOL_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TASK_PYTHON=${PYTHON:-python3}
"$TASK_PYTHON" -c 'import sys; assert sys.version_info >= (3,9), "Python 3.9+ required"'
if [ ! -x "$TOOL_DIR/.venv/bin/python" ]; then
    "$TASK_PYTHON" -m venv "$TOOL_DIR/.venv"
fi
"$TOOL_DIR/.venv/bin/python" -m pip install --disable-pip-version-check -r "$TOOL_DIR/requirements.txt"
"$TOOL_DIR/.venv/bin/python" "$TOOL_DIR/scripts/wechat_draft.py" --help
