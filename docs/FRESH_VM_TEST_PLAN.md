# Fresh-VM Install Test Plan

How to repeatedly validate that the **whole gmux-system stack installs
and runs cleanly on a completely fresh machine**. Complements
`EFFICIENT_DEPLOY.md` (which describes the deploy tool) and
`VM_PROTOCOL.md` (which describes the existing sandbox VM).

**Why this matters:** The sandbox VM has been mutated over many sessions
— packages installed by ad-hoc commands, stale processes, lingering
config. We need a clean-room test where each run starts from a known
baseline so we can catch deploy-script regressions.

---

## Three test rigs to keep around

### Rig A — Existing `sandbox` VM (long-running, mutated)
- Always there, fast to deploy to
- Catches regressions in deploy logic against an "established" install
- Use for: day-to-day deploy verification, the v3.6.3 `./scripts/deploy.sh sandbox` flow
- Documented: `docs/VM_PROTOCOL.md`

### Rig B — Fresh-snapshot VM (clean each run)
- A QEMU VM with a known-good snapshot we revert to before every test
- Mutations from the test run are discarded
- Use for: validating install-vm.sh end-to-end, catching missed dependencies
- **This doc covers building this rig**

### Rig C — Cloud disposable (e.g. fresh Hetzner / DigitalOcean droplet)
- API-driven create-destroy cycle
- Costs pennies per test (~€0.005/hour)
- Use for: validating install on actual Debian/Ubuntu cloud images (the
  sandbox is CachyOS only)
- Future: GitHub Actions can run this on every push

---

## Building Rig B — fresh-snapshot QEMU VM

### One-time setup

```bash
# 1. Pick a stable base image. Recommendations:
#    CachyOS minimal ISO   ~1.5 GB, our reference OS
#    Debian 12 cloud image ~250 MB, the "stranger" test
#    Ubuntu 24.04 server   ~700 MB, widely used

# 2. Build a VM disk image (KVM/QEMU):
qemu-img create -f qcow2 ~/vm-images/gmux-fresh.qcow2 20G

# 3. Boot from the ISO, install OS minimally, enable sshd, create
#    'agent' user with sudo. Then power off.

# 4. Snapshot the clean install:
qemu-img snapshot -c clean-install ~/vm-images/gmux-fresh.qcow2

# 5. Note the snapshot name; revert to it before every test:
qemu-img snapshot -a clean-install ~/vm-images/gmux-fresh.qcow2
```

### Boot helper script

Create `scripts/vm-fresh-boot.sh`:
```bash
#!/usr/bin/env bash
# Boot a clean snapshot of the fresh-test VM in headless mode.
set -e
IMG=~/vm-images/gmux-fresh.qcow2
SNAP=clean-install
SSH_PORT=2299

qemu-img snapshot -a "$SNAP" "$IMG"
qemu-system-x86_64 \
  -m 4G -smp 2 -enable-kvm \
  -drive file="$IMG",if=virtio \
  -nic user,hostfwd=tcp::$SSH_PORT-:22 \
  -display none -daemonize \
  -pidfile /tmp/gmux-fresh-vm.pid

# Wait for SSH
for i in {1..60}; do
  if ssh -p $SSH_PORT -o StrictHostKeyChecking=no \
         -o UserKnownHostsFile=/dev/null -o ConnectTimeout=1 \
         agent@127.0.0.1 'echo ok' 2>/dev/null; then
    echo "VM up on localhost:$SSH_PORT"
    exit 0
  fi
  sleep 1
done
echo "VM did not come up in 60s"
exit 1
```

`~/.ssh/config`:
```
Host gmux-fresh
  HostName 127.0.0.1
  Port 2299
  User agent
  StrictHostKeyChecking no
  UserKnownHostsFile /dev/null
```

Now `ssh gmux-fresh` reaches the fresh VM.

---

## The test cycle

### Single-pass test (manual)

```bash
# 1. Boot fresh
./scripts/vm-fresh-boot.sh

# 2. Run the deploy
./scripts/deploy.sh gmux-fresh

# 3. Verify everything green
ssh gmux-fresh 'bash ~/projects/gmux-system/scripts/install-vm.sh' \
  | tee /tmp/install-log

# 4. Functional checks (from host)
curl --max-time 3 http://127.0.0.1:8769/health      # via ssh tunnel? See below
ssh gmux-fresh 'curl -s http://127.0.0.1:8769/health'

# 5. Tear down
kill $(cat /tmp/gmux-fresh-vm.pid)
```

### Automated test loop

`scripts/test-fresh-install.sh` (new — write this for v3.8):
```bash
#!/usr/bin/env bash
# Full-cycle fresh-install verification.
# Boots fresh VM, deploys, runs checks, captures result.
set -e

LOG=/tmp/gmux-fresh-test-$(date +%Y%m%d-%H%M%S).log
exec > >(tee -a "$LOG") 2>&1

echo "=== fresh VM boot ==="
./scripts/vm-fresh-boot.sh

echo "=== deploy ==="
./scripts/deploy.sh gmux-fresh

echo "=== install-vm.sh verbose ==="
ssh gmux-fresh 'bash ~/projects/gmux-system/scripts/install-vm.sh'

echo "=== checks ==="
ssh gmux-fresh '
  set -e
  echo "1. health"      && curl -s --max-time 3 http://127.0.0.1:8769/health
  echo "2. producers"   && ls /tmp/gmuxtest-*.json | wc -l
  echo "3. python deps" && python3 -c "import psutil, websockets; print(\"ok\")"
  echo "4. opencode"    && ~/.bun/bin/opencode --version
  echo "5. tests"       && cd ~/projects/gmux-system && python3 backend/status/test_monitor_producers.py | tail -1
  echo "6. sub_agent"   && python3 backend/status/test_sub_agents.py | tail -1
  echo "7. memory"      && python3 backend/status/test_memory_aggregator.py | tail -1
  echo "8. tmux"        && tmux ls
  echo "9. ports"       && ss -tlnp 2>/dev/null | grep -E ":(5550|8769)"
'

echo "=== teardown ==="
kill $(cat /tmp/gmux-fresh-vm.pid)

echo "=== summary ==="
echo "Log saved to: $LOG"
```

Pass criteria for each numbered check is documented inline.

---

## What to test in the fresh VM specifically

Most of these are already covered by `VM_PROTOCOL.md`'s Step 9 checklist
but worth re-stating in clean-room context:

### Mandatory (every test cycle)
- [ ] `install-vm.sh` completes without errors on a system that has NEVER
      run gmux before
- [ ] All system packages installed (tmux, python3, git, curl, rsync)
- [ ] Python deps installed (`psutil`, `websockets`, `requests`)
- [ ] `bun` installed at `~/.bun/bin/bun`
- [ ] `opencode-ai` installed (binary called `opencode`)
- [ ] tmux session `gmux` created
- [ ] `monitor.py` running (use `setsid`, survives ssh disconnect)
- [ ] `http.server` on `:5550` bound to `0.0.0.0`
- [ ] `/tmp/gmuxtest-*.json` all 5 producer files present
- [ ] `/health` returns `ok`
- [ ] `/api/state` returns JSON
- [ ] UI HTML reachable on `:5550`
- [ ] All test suites pass (147 / 30 / 64 = 241 tests)

### Smoke (every 5th cycle)
- [ ] Run `gmux pair` (when implemented in v3.8) and validate QR
- [ ] Connect a phone (PWA in browser) to the VM's bridge
- [ ] Spawn an opencode agent and confirm pane appears in API state
- [ ] Watch activity feed populate when agent runs a tool

### Stress (every 10th cycle)
- [ ] Spawn 20 agents simultaneously; confirm monitor.py stays under 100 MB RSS
- [ ] Kill monitor.py mid-run; restart; verify producer files come back
- [ ] Disconnect SSH; verify `setsid`-spawned processes survive
- [ ] Send the `restart` signal to monitor and verify clean restart

---

## What "fresh" actually means

The fresh-snapshot VM has:
- ✅ Base OS only (CachyOS / Debian / Ubuntu, depending on which image)
- ✅ ssh-server running
- ✅ The `agent` user with sudo (no password)
- ✅ Empty `~/`
- ❌ No tmux installed
- ❌ No python pip packages
- ❌ No bun / opencode
- ❌ No `~/projects/gmux-system/`
- ❌ No `~/.local/share/opencode/`
- ❌ No tmux session

This is the realistic "new user just got a VM and tried it" baseline.

---

## When to use this rig

| Scenario | Use |
|---|---|
| Daily dev iteration | sandbox (Rig A) — fast |
| About to cut a release tag | fresh-snapshot (Rig B) — clean-room |
| Investigating a user-reported install failure | fresh-snapshot of their distro |
| Pre-flight before pushing to public GitHub | fresh-snapshot + Debian + Ubuntu (Rig C) |
| Cross-distro coverage | matrix: CachyOS, Debian, Ubuntu, Fedora |

---

## Future: GitHub Actions matrix (v3.9+)

```yaml
# .github/workflows/install-test.yml
name: Fresh install verification
on: [push, pull_request]
jobs:
  test-install:
    strategy:
      matrix:
        os: [ubuntu-22.04, ubuntu-24.04, debian-12]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - run: bash scripts/install-vm.sh
      - run: python3 backend/status/test_monitor_producers.py
      - run: python3 backend/status/test_sub_agents.py
      - run: python3 backend/status/test_memory_aggregator.py
```

This catches "doesn't install on Ubuntu" regressions in CI before they
hit users. Not needed yet (single-user project) but easy to enable when
the user base grows.

---

## Combined test pass — full stack

Combines this fresh-VM rig with the phone app (gmux-phone) to test the
entire user journey:

1. Fresh-snapshot VM boots
2. Host runs `./scripts/deploy.sh gmux-fresh`
3. Host runs `gmux pair` → QR appears
4. Phone (in browser) scans QR → connects to VM's bridge
5. Phone shows the empty VM with no agents
6. Phone taps "+" → spawns an agent → pane appears
7. Agent runs a tool → activity flows to phone
8. Phone approves a permission → tmux pane gets `y\n`
9. Phone kills the agent → pane disappears
10. All test assertions pass; tear down VM

That's the full integration test. Run it before every major release.

---

## What this rig does NOT cover

- Tauri desktop app on the VM (no display server — see `MACOS_PORTING.md`
  and `VM_PROTOCOL.md` for the "headless can't run Tauri" note)
- macOS install (no macOS in CI; only manual)
- Real provider API auth (we mock or use a throwaway test account)
- Multi-tenant scenarios (one user per VM here)

These remain manual tests.

---

## Failure-mode capture

When a test cycle fails, save:

1. Full install log → `/tmp/gmux-fresh-test-<timestamp>.log` (already done)
2. Last 100 lines of `/tmp/gmux-monitor.log` from the VM
3. `pgrep -af monitor.py http.server` snapshot
4. `ls -la /tmp/gmuxtest-*.json` snapshot
5. Producer JSON contents (first 200 bytes each)

Copy back to host:
```bash
ssh gmux-fresh 'tar czf /tmp/failure-bundle.tar.gz \
  /tmp/gmux-*.log /tmp/gmuxtest-*.json ~/.config/gmux/ 2>/dev/null'
scp gmux-fresh:/tmp/failure-bundle.tar.gz docs/VM_REPORTS/failure-$(date +%s).tar.gz
```

Open a `docs/VM_REPORTS/<date>-failure-<short>.md` with the analysis.

---

## Quick reference

| Action | Command |
|---|---|
| Boot fresh | `./scripts/vm-fresh-boot.sh` |
| Deploy | `./scripts/deploy.sh gmux-fresh` |
| Run all checks | `./scripts/test-fresh-install.sh` |
| Tear down | `kill $(cat /tmp/gmux-fresh-vm.pid)` |
| Capture failure | `ssh gmux-fresh 'tar czf /tmp/failure.tar.gz /tmp/gmux-*.log /tmp/gmuxtest-*.json'` |

When everything's solid: tag a release, push to GitHub, the install
script in the README is guaranteed to work for a stranger trying it.
