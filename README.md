# Helix Client for Termux

Android Termux client for the [Helix](https://github.com/RGHwiskzero/helix-client-termux) local network terminal manager. Each phone registers its own name and cryptographic identity locally. No shared password or device key is stored in this repository.

Open Termux from F-Droid and run:

```bash
pkg install -y git && git clone https://github.com/RGHwiskzero/helix-client-termux.git "$HOME/helix-client-termux" && bash "$HOME/helix-client-termux/install.sh"
```

On first launch, enter a device name and the current shared password configured on your Debian Helix host. On Debian, run `index`, then `list connected`, then `connect <ID>`. Inside the phone's remote Bash shell, run `disconnect` to return to the host.

Read [USER_GUIDE.md](USER_GUIDE.md) for usage and limits, and [AGENT_GUIDE.md](AGENT_GUIDE.md) for protocol and agent operation. Real Android installation and LAN behavior still need a phone test.
