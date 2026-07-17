#!/bin/bash
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "Complexation Property Explorer"
echo "The first start can take several minutes. Keep this window open."
echo
if ! "$PROJECT_DIR/run.sh"; then
  echo
  read -r -p "Press Return to close this window."
  exit 1
fi
