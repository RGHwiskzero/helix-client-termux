# Helix Termux client: guide for coding agents

## Scope

This directory is the Android Termux client package for Helix protocol v1. It is intended to be published separately from `helix-host`, because the host source and runtime state are private. Never add a shared password, `client_config.json`, a private key, or a host `devices.json` to this package or its repository. The client asks for a password on first launch and generates its own UUID, TLS keypair, and `auth_key` under `~/.config/helix-client-termux/` on each phone.

The Debian host remains the controller. The Termux client listens for discovery and one remote terminal session at a time. No internet-facing service, Android root privileges, Android boot service, PRoot Debian, GUI, or game server is installed by this package.

## Files and launch

- `install.sh` installs Termux packages `python`, `openssl`, and `tmux`, creates a `hlx-client` symlink, and adds a guarded interactive Bash hook. The hook skips remote Helix shells via `HELIX_REMOTE_SHELL=1`.
- `launch-client.sh` attaches to or creates the single tmux session named `helix-client`. It uses the source directory resolved from its symlink. `quit` ends the Python client; Ctrl+B then D only detaches.
- `helix_client_termux.py` implements local setup, authentication, discovery, TLS listener, terminal frames, and the local command prompt.
- `termux_pty_worker.py` is a separate process because `pty.fork()` must not be called in the multithreaded listener. It relays raw bytes between pipes and a Bash PTY.
- `remote_shell_rc.sh` sources the phone's `.bashrc` and defines a Bash `disconnect` function that exits the remote shell. It runs with `HELIX_REMOTE_SHELL=1` to avoid recursive client startup.
- `helix_protocol.py` is copied from the host. Keep its version, frame encoding, signatures, KDF, and ports synchronized with the host and Windows client.

The Termux client uses Python's standard library and the Termux OpenSSL binary. It does not need a Python cryptography package. `openssl req` generates a unique self-signed RSA certificate; Python `ssl.PEM_cert_to_DER_cert` computes its pinned SHA-256 fingerprint. The private key and config are owner-only files within Termux's private home.

## Protocol

The host sends UDP `{"type":"discover","version":1,"nonce":"<32 hex>"}` to port `49321`. The client replies with an HMAC-signed offer containing `type`, `version`, echoed `nonce`, `client_id`, `name`, `platform:"termux"`, `port:49322`, and `certificate_sha256`. The first phone registration derives `auth_key = HMAC-SHA256(PBKDF2-HMAC-SHA256(shared_password, "Helix discovery v1", 310000), "client:" + client_id)`. Never send the password in discovery. The host saves each indexed client's key and TLS fingerprint in its private `devices.json`.

The host opens TLS TCP to port `49322`, verifies the exact certificate fingerprint, receives a fresh challenge, signs an authenticate payload with the saved `auth_key`, and sends an `open` frame with terminal dimensions. The client starts one Bash PTY and replies `opened`. `input` and `output` frames carry base64 raw terminal bytes. `close` or shell exit ends the session. The host currently does not automatically send resize frames; the client ignores them in this first version.

The client startup password is checked locally using a salted PBKDF2 hash. `client> password` changes this local hash while leaving the saved `auth_key` intact, so an indexed host can reconnect. `host password` on Debian changes the password for host login and **new** client discovery, while existing indexed clients retain their stored keys. Re-index after a LAN address change. If certificate identity is intentionally reset, remove the host's old device entry before indexing again.

## Agent operation

Use the Debian `hlx` interface: `index`, `list connected`, `connect <ID>`. Verify the ID and device name before operating it. Commands after connecting execute in the phone's Termux Bash with Termux's permissions. Type `disconnect` in the remote Bash or use Ctrl+] and `disconnect` at the host prompt. Do not mistake a remote phone prompt for the Debian host. For host commands during a remote session, use Ctrl+] and `host <command>`.

Termux owns app-private files and may access shared storage after the user runs `termux-setup-storage` and grants permission. A non-root Termux shell is not an Android system shell. When planning package installs or long-running servers, verify actual Termux/Android support first. Do not claim a real phone test from local protocol tests.

## Verification boundary

On the Windows development machine, syntax, protocol compatibility, registration, TLS authentication, and installer text can be checked. The PTY, Termux package installation, tmux startup, Android background lifetime, and real LAN discovery need a physical Termux test before they are considered verified.
