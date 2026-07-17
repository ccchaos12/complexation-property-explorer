#!/bin/bash
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
if ! "$PROJECT_DIR/run.sh"; then
  echo
  read -r -p "Press Return to close this window."
  exit 1
fi
