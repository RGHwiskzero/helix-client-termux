# Helix Client for Android Termux

This folder contains a Helix v1 client for Android Termux. It joins the same local network as the Debian Helix host and provides an interactive Termux Bash terminal when the host uses `connect <ID>`. No root access or separate APK is needed for this client. It cannot control Android system features that Termux itself cannot access.

## Install

Install Termux from F-Droid and open it once. Keep the phone and Debian host on the same local network. Install from the public client repository with one command in Termux:

```bash
pkg install -y git && git clone https://github.com/RGHwiskzero/helix-client-termux.git "$HOME/helix-client-termux" && bash "$HOME/helix-client-termux/install.sh"
```

To install from files copied to the phone instead, run `bash install.sh` inside this folder.

The installer uses Termux's `pkg` to install Python, OpenSSL, and tmux. It creates `~/.local/bin/hlx-client`, adds an idempotent interactive Bash startup hook to `~/.bashrc`, and starts the client. Keep the installed folder in place: the launcher points to it. Re-running the installer is safe for the same folder, but it refuses to replace an unrelated `hlx-client` launcher.

On first launch, enter a device name and the current shared Helix password. The program creates a unique client ID, authentication key, and TLS certificate on the phone. **No password, key, certificate, or device identity belongs in the public repository.** The private files are stored under `~/.config/helix-client-termux/`. On later launches, enter the local client password. The client stays open in a tmux session; opening Termux again attaches to it. If Android stopped the process, opening Termux starts it again and asks for the password.

To detach while keeping the client running, press **Ctrl+B**, then **D**. Type `hlx-client` in a Termux shell to reattach. Type `quit` at `client>` to stop the client. The next Termux launch starts it again. This is Termux-open autostart; it does not start at Android boot. Android can stop Termux while the phone is idle, so the host may need the phone reopened before `index` or `connect` works.

## Connect from Debian

Start `hlx` on Debian and enter its password. Then:

```text
hlx> index
hlx> list connected
hlx> connect <ID>
```

The remote prompt is a Bash shell inside Termux. Ordinary commands execute on the phone with Termux's app permissions. `disconnect` closes that remote shell and returns to Debian's `hlx>` prompt. **Ctrl+]** opens the Helix host's local command prompt; there you can run `host <Debian command>` or `disconnect` without sending the command to the phone.

The host can reconnect to a previously indexed phone using its saved device ID and key. When the phone's LAN address changes, run `index` again to update the saved address. Each phone needs its own installation and first-run registration.

## Local client commands

| Command at `client>` | Action |
| --- | --- |
| `help` | Show local commands. |
| `status` | Show the registered device and whether a remote session is active. |
| `password` | Change the local password used when starting this client. Existing host pairing remains valid. |
| `quit` | Stop the client process. |

The `password` command does not rotate the host's password or the pairing key. For a new phone, use the host's **current** discovery password. If the host password changed after another phone was indexed, the older phone can still connect using its stored pairing key.

## Phone files and limits

Termux can access its own `$HOME` directly. To grant access to Android shared storage (for example, `Download`), run `termux-setup-storage` on the phone and accept Android's permission prompt. Shared storage access is optional for Helix itself. Android `proot-distro`, graphical access, and game server installation are separate future steps and are not installed by this package.

If `index` does not find the phone, check that `client>` says ready, both devices use the same LAN, and the Wi-Fi does not isolate clients. Helix uses UDP `49321` for discovery and TCP `49322` for encrypted terminal sessions. Mobile data, VPNs, and internet access are outside this version's scope.

## Updating and protecting state

Update only the source folder. Keep `~/.config/helix-client-termux/` unchanged or the host will reject the changed TLS identity. Do not copy private state between phones. If you intentionally reset a phone's identity, remove its old record from the host's `devices.json` while Helix is stopped, then run `index` with the current shared password.

The real Android-to-Debian discovery and terminal test still has to be performed on a phone. This package was checked on the development machine, which cannot reproduce Android's process and network behavior.
