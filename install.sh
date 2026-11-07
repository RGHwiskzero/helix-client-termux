#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

if [[ ${PREFIX:-} != *com.termux* ]]; then
    printf 'Run this installer inside Android Termux.\n' >&2
    exit 1
fi

app_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
launcher="$HOME/.local/bin/hlx-client"
target="$app_dir/launch-client.sh"

printf 'Installing Termux packages...\n'
pkg install -y python openssl openssl-tool tmux
mkdir -p -- "$HOME/.local/bin"
if [[ -L $launcher ]]; then
    if [[ $(readlink -f -- "$launcher") != "$target" ]]; then
        printf 'A different hlx-client launcher already exists: %s\n' "$launcher" >&2
        exit 1
    fi
    rm -- "$launcher"
elif [[ -e $launcher ]] && ! grep -Fqx '# Managed by Helix Termux install.sh' "$launcher"; then
    printf 'A different hlx-client launcher already exists: %s\n' "$launcher" >&2
    exit 1
fi
printf -v target_quoted '%q' "$target"
{
    printf '#!%s/bin/bash\n' "$PREFIX"
    printf '%s\n' '# Managed by Helix Termux install.sh'
    printf 'exec %q %s "$@"\n' "$PREFIX/bin/bash" "$target_quoted"
} > "$launcher"
chmod 700 -- "$launcher"
export PATH="$HOME/.local/bin:$PATH"

bashrc="$HOME/.bashrc"
if ! grep -Fq '# BEGIN HELIX CLIENT AUTOSTART' "$bashrc" 2>/dev/null; then
    cat >> "$bashrc" <<'HOOK'

# BEGIN HELIX CLIENT AUTOSTART
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) export PATH="$HOME/.local/bin:$PATH" ;;
esac
if [[ $- == *i* && -z ${HELIX_REMOTE_SHELL:-} && -z ${HELIX_CLIENT_AUTOSTARTED:-} ]]; then
    export HELIX_CLIENT_AUTOSTARTED=1
    "$HOME/.local/bin/hlx-client" --start
fi
# END HELIX CLIENT AUTOSTART
HOOK
fi

printf '\nInstalled. Starting Helix Client...\n'
"$launcher" --start
