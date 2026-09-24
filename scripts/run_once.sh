#!/bin/zsh

SCRIPT_DIR=${0:A:h}
PROJECT_DIR=${SCRIPT_DIR:h}

cd "$PROJECT_DIR" || exit 1
exec /usr/bin/env python3 -u main.py --headless --mode all
