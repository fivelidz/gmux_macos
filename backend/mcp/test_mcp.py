#!/usr/bin/env python3.11
"""
Test script for gmux_mcp.py.

Spawns gmux_mcp.py as a subprocess, performs the full MCP handshake,
calls tools/list, then calls gmux_health and gmux_list_panes.

Exit 0 on success, nonzero on failure.
"""

import io
import json
import os
import select
import subprocess
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MCP_SERVER = os.path.join(SCRIPT_DIR, "gmux_mcp.py")
PYTHON = "/usr/bin/python3.11"  # explicit to match the shebang

TIMEOUT = 10  # seconds per response


# ──────────────────────────────────────────────────────────────────────────────
# Subprocess helpers
# ──────────────────────────────────────────────────────────────────────────────


def send_msg(proc: "subprocess.Popen[bytes]", msg: dict) -> None:
    assert proc.stdin is not None
    line = json.dumps(msg) + "\n"
    proc.stdin.write(line.encode())
    proc.stdin.flush()


def recv_msg(proc: "subprocess.Popen[bytes]", timeout: float = TIMEOUT) -> dict:
    """Read one newline-terminated JSON message from the server stdout."""
    assert proc.stdout is not None
    deadline = time.monotonic() + timeout
    buf: bytes = b""
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"No response within {timeout}s. Partial: {buf!r}")
        rlist, _, _ = select.select([proc.stdout], [], [], min(remaining, 0.5))
        if rlist:
            chunk: bytes = proc.stdout.read1(4096)  # type: ignore[union-attr]
            if not chunk:
                raise EOFError("Server closed stdout unexpectedly")
            buf += chunk
            if b"\n" in buf:
                line_b, _, _ = buf.partition(b"\n")
                return json.loads(line_b.decode())
        if proc.poll() is not None:
            raise RuntimeError(f"Server exited (code {proc.returncode}). buf={buf!r}")


def rpc(
    proc: "subprocess.Popen[bytes]", method: str, params: dict, req_id: int
) -> dict:
    send_msg(
        proc,
        {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        },
    )
    resp = recv_msg(proc)
    assert resp.get("id") == req_id, (
        f"id mismatch: expected {req_id}, got {resp.get('id')}"
    )
    return resp


def notify(proc: "subprocess.Popen[bytes]", method: str, params: dict) -> None:
    send_msg(
        proc,
        {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# Test runner
# ──────────────────────────────────────────────────────────────────────────────

PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "


def run_tests() -> int:
    failures = 0

    print(f"\n{'=' * 60}")
    print(f"  gmux MCP server test")
    print(f"  server: {MCP_SERVER}")
    print(f"  python: {PYTHON}")
    print(f"{'=' * 60}\n")

    # ── Start server ──────────────────────────────────────────────────────────
    print("Starting MCP server subprocess...")
    proc: "subprocess.Popen[bytes]" = subprocess.Popen(
        [PYTHON, MCP_SERVER],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    print(f"  pid: {proc.pid}")

    time.sleep(0.3)
    if proc.poll() is not None:
        assert proc.stderr is not None
        stderr_txt = proc.stderr.read().decode(errors="replace")
        print(f"{FAIL} Server exited immediately. stderr:\n{stderr_txt}")
        return 1

    try:
        # ── TEST 1: initialize ────────────────────────────────────────────────
        print("\n[1] MCP initialize handshake")
        resp = rpc(
            proc,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "test-client", "version": "0.1"},
                "capabilities": {},
            },
            req_id=1,
        )

        if "error" in resp:
            print(f"  {FAIL} initialize error: {resp['error']}")
            failures += 1
        else:
            result = resp.get("result", {})
            proto = result.get("protocolVersion")
            server = result.get("serverInfo", {}).get("name")
            print(f"  {PASS} protocolVersion={proto!r}  server={server!r}")

        notify(proc, "notifications/initialized", {})
        time.sleep(0.1)

        # ── TEST 2: tools/list ────────────────────────────────────────────────
        print("\n[2] tools/list")
        resp = rpc(proc, "tools/list", {}, req_id=2)

        if "error" in resp:
            print(f"  {FAIL} tools/list error: {resp['error']}")
            failures += 1
        else:
            tools = resp.get("result", {}).get("tools", [])
            names = [t["name"] for t in tools]
            expected = {
                "gmux_health",
                "gmux_list_panes",
                "gmux_pane_messages",
                "gmux_pane_todos",
                "gmux_spawn_agent",
                "gmux_spawn_sub_agent",
                "gmux_send_text",
                "gmux_send_key",
                "gmux_respond_permission",
            }
            missing = expected - set(names)
            if missing:
                print(f"  {FAIL} missing tools: {missing}")
                failures += 1
            else:
                print(f"  {PASS} {len(tools)} tools listed:")
                for n in sorted(names):
                    print(f"         - {n}")

        # ── TEST 3: gmux_health ───────────────────────────────────────────────
        print("\n[3] gmux_health")
        resp = rpc(
            proc,
            "tools/call",
            {
                "name": "gmux_health",
                "arguments": {},
            },
            req_id=3,
        )

        if "error" in resp:
            print(f"  {FAIL} RPC error: {resp['error']}")
            failures += 1
        else:
            content = resp.get("result", {}).get("content", [])
            is_err = resp.get("result", {}).get("isError", False)
            if content:
                health = json.loads(content[0]["text"])
                monitor_up = health.get("monitor_up", False)
                bridge_up = health.get("bridge_up", False)
                token_ok = health.get("token_loaded", False)

                if monitor_up:
                    print(f"  {PASS} monitor reachable at {health.get('monitor_url')}")
                else:
                    print(
                        f"  {FAIL} monitor NOT reachable: {health.get('monitor_error')}"
                    )
                    failures += 1

                if bridge_up:
                    print(f"  {PASS} bridge reachable at {health.get('bridge_url')}")
                else:
                    print(
                        f"  {WARN} bridge NOT reachable (acceptable if not running): "
                        f"{health.get('bridge_error')}"
                    )

                if token_ok:
                    print(f"  {PASS} token loaded: {health.get('token_preview')}")
                else:
                    print(f"  {WARN} no auth token (write tools will refuse)")

                print(f"\n  Raw health dict:")
                print(json.dumps(health, indent=4))
            else:
                print(f"  {FAIL} no content in response")
                failures += 1

        # ── TEST 4: gmux_list_panes ───────────────────────────────────────────
        print("\n[4] gmux_list_panes")
        resp = rpc(
            proc,
            "tools/call",
            {
                "name": "gmux_list_panes",
                "arguments": {},
            },
            req_id=4,
        )

        if "error" in resp:
            print(f"  {FAIL} RPC error: {resp['error']}")
            failures += 1
        else:
            content = resp.get("result", {}).get("content", [])
            is_err = resp.get("result", {}).get("isError", False)
            if is_err:
                err_text = content[0]["text"] if content else "(no content)"
                print(f"  {FAIL} tool returned error: {err_text}")
                failures += 1
            elif content:
                panes = json.loads(content[0]["text"])
                print(f"  {PASS} {len(panes)} pane(s) returned")
                for p in panes:
                    print(
                        f"         pane_id={p['pane_id']!r:10s} "
                        f"session={p['session_name']!r:20s} "
                        f"window={p['window_name']!r:35s} "
                        f"has_ai={p['has_ai']!r}"
                    )
            else:
                print(f"  {FAIL} no content in response")
                failures += 1

        # ── TEST 5: unknown method → -32601 ───────────────────────────────────
        print("\n[5] unknown method → expect -32601")
        resp = rpc(proc, "nonexistent/method", {}, req_id=5)
        if "error" in resp and resp["error"].get("code") == -32601:
            print(f"  {PASS} correct -32601 error returned")
        else:
            print(f"  {FAIL} unexpected response: {resp}")
            failures += 1

    except Exception as exc:
        print(f"\n{FAIL} Unexpected test exception: {exc}")
        import traceback

        traceback.print_exc()
        failures += 1
    finally:
        assert proc.stdin is not None
        assert proc.stderr is not None
        proc.stdin.close()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        stderr_out = proc.stderr.read().decode(errors="replace")
        if stderr_out.strip():
            print(f"\n── Server stderr ──\n{stderr_out}")

    print(f"\n{'=' * 60}")
    if failures == 0:
        print(f"  {PASS} ALL TESTS PASSED")
    else:
        print(f"  {FAIL} {failures} TEST(S) FAILED")
    print(f"{'=' * 60}\n")

    return failures


if __name__ == "__main__":
    sys.exit(run_tests())
