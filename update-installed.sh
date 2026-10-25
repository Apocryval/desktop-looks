#!/bin/sh
exec /usr/bin/python3 "$(dirname -- "$0")/migrate.py" --apply
