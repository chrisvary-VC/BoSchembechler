#!/bin/zsh
set -euo pipefail

project_root="${0:A:h:h}"
runtime_dir="$project_root/.runtime"
mkdir -p "$runtime_dir"
print -n -- "" > "$runtime_dir/public-url.txt"

/opt/homebrew/opt/cloudflared/bin/cloudflared tunnel \
  --url http://127.0.0.1:4310 \
  --no-autoupdate 2>&1 | while IFS= read -r line; do
  print -r -- "$line"
  if [[ "$line" =~ '(https://[a-z0-9-]+\.trycloudflare\.com)' ]]; then
    print -r -- "$match[1]" > "$runtime_dir/public-url.txt"
  fi
done
