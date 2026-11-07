#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

if [[ ${1:-} != "" && ${1:-} != "--start" ]]; then
    printf 'Usage: hlx-client [--start]\n' >&2
    exit 2
fi

app_dir=$(dirname -- "$(readlink -f -- "$0")")
session=helix-client
if ! tmux has-session -t "$session" 2>/dev/null; then
    printf -v task '%q %q' "$PREFIX/bin/python" "$app_dir/helix_client_termux.py"
    tmux new-session -d -s "$session" -c "$HOME" "$task || { printf '%s\n' 'Helix Client stopped with an error. Press Enter to close.'; read -r; }"
fi

if [[ -n ${TMUX:-} ]]; then
    tmux switch-client -t "$session"
else
    tmux attach-session -t "$session"
fi
