"""
diagnose_atlas_tls.py — Run a raw TLS handshake to each Atlas shard from
inside the Cloud Run container and dump the result to stdout.

This is the canonical test for ruling pymongo in/out of the failure path:
- If openssl ALSO gets TLSV1_ALERT_INTERNAL_ERROR → problem is purely Atlas-side
  for this source IP and only an M2+ upgrade (or different cluster) fixes it.
- If openssl handshake SUCCEEDS → pymongo itself is doing something different,
  and there's still a code-side fix to chase.

Runs once at container startup, then exits.  Never raises — diagnostic only.
"""

from __future__ import annotations

import socket
import subprocess
import sys

SHARDS = [
    ("ac-ctazhbz-shard-00-00.wwrd9ag.mongodb.net", 27017),
    ("ac-ctazhbz-shard-00-01.wwrd9ag.mongodb.net", 27017),
    ("ac-ctazhbz-shard-00-02.wwrd9ag.mongodb.net", 27017),
]


def _say(msg: str) -> None:
    print(msg, flush=True)


def _probe_dns(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, None)
        ips = sorted({i[4][0] for i in infos})
        _say(f"[TLS-DIAG] DNS {host} -> {ips}")
    except Exception as exc:  # noqa: BLE001
        _say(f"[TLS-DIAG] DNS {host} FAILED: {exc}")


def _probe_tls(host: str, port: int, tls_flag: str) -> None:
    label = f"{host}:{port} via {tls_flag}"
    _say(f"\n[TLS-DIAG] ---- BEGIN {label} ----")
    try:
        proc = subprocess.run(
            [
                "openssl", "s_client",
                "-connect", f"{host}:{port}",
                "-servername", host,
                tls_flag,
                "-brief",
            ],
            input="",
            capture_output=True,
            text=True,
            timeout=15,
        )
        _say(f"[TLS-DIAG] return_code={proc.returncode}")
        if proc.stdout:
            _say("[TLS-DIAG] STDOUT:")
            for line in proc.stdout.splitlines():
                _say(f"  {line}")
        if proc.stderr:
            _say("[TLS-DIAG] STDERR:")
            for line in proc.stderr.splitlines():
                _say(f"  {line}")
    except subprocess.TimeoutExpired:
        _say("[TLS-DIAG] TIMEOUT after 15s")
    except FileNotFoundError:
        _say("[TLS-DIAG] openssl binary not found in container PATH")
    except Exception as exc:  # noqa: BLE001
        _say(f"[TLS-DIAG] Unexpected error: {exc}")
    _say(f"[TLS-DIAG] ---- END   {label} ----")


def main() -> None:
    _say("\n" + "=" * 70)
    _say("[TLS-DIAG] MongoDB Atlas TLS handshake diagnostic")
    _say("[TLS-DIAG] Source: this Cloud Run container's egress IP")
    _say("[TLS-DIAG] Target: Atlas M0 shard replica set")
    _say("=" * 70)

    # Note the public IP we appear as
    try:
        ip = subprocess.run(
            ["curl", "-s", "--max-time", "5", "https://ifconfig.me"],
            capture_output=True, text=True, timeout=8,
        ).stdout.strip()
        _say(f"[TLS-DIAG] My egress IP (via ifconfig.me): {ip or '<empty>'}")
    except Exception as exc:  # noqa: BLE001
        _say(f"[TLS-DIAG] ifconfig.me check failed: {exc}")

    for host, port in SHARDS:
        _probe_dns(host)

    # Test TLS 1.2 only against the first shard (most representative)
    host, port = SHARDS[0]
    _probe_tls(host, port, "-tls1_2")
    # And TLS 1.3 to see if alert text differs by version
    _probe_tls(host, port, "-tls1_3")

    _say("\n" + "=" * 70)
    _say("[TLS-DIAG] Diagnostic complete — proceeding with Streamlit startup")
    _say("=" * 70 + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        _say(f"[TLS-DIAG] FATAL diagnostic error: {exc}")
    # Never block startup
    sys.exit(0)
