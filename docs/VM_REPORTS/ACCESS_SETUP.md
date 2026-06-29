# Ashley's MacBook — Remote Access Setup

Established 2026-06-29 from `superlocal` (fivelidz CachyOS).

## Connection
- **SSH alias:** `ssh ashmac`  (configured in `~/.ssh/config` on superlocal)
- **Host:** `100.92.187.3` (Tailscale IP, tailnet `tail5facd1.ts.net`)
- **User:** `ashleychapman-davies`
- **Auth:** ed25519 public key (`fivelidz@superlocal`) in the Mac's `~/.ssh/authorized_keys` — passwordless
- **Machine:** macOS 12.7.6 Monterey, Intel x86_64, 367 GB free

## Persistence (survives reboot)
- **sshd:** system LaunchDaemon `/System/Library/LaunchDaemons/ssh.plist` — Remote Login = On
- **Tailscale:** standalone app (system extension) + added as a **login item** (hidden) so the
  tunnel rejoins the tailnet on boot
- **CLI:** symlinked `/usr/local/bin/tailscale -> /Applications/Tailscale.app/Contents/MacOS/Tailscale`
- **Passwordless sudo:** `/etc/sudoers.d/gmux-admin` grants `ashleychapman-davies ALL=(ALL) NOPASSWD: ALL`

## Long-term durability — what could break access (and the fix)
- **Tailscale node key expiry** → DISABLE in admin console:
  https://login.tailscale.com/admin/machines → ashleys-macbook-pro → ⋯ → Disable key expiry
- **Ashley changes GitHub account** → no effect (separate system)
- **Ashley runs `tailscale logout` / uninstalls Tailscale** → would cut access
- **Ashley turns off Remote Login** → would cut access
- **Ashley removes the authorized_keys line or sudoers file** → would cut access

## NOT affected
- Changing the GitHub account on the Mac does NOT affect Tailscale or SSH access.

## Security note
- An invite link was pasted into chat earlier — revoke it in Tailscale admin → Settings → Invites.
