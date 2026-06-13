"""
diagnose_atlas_tls.py — Run a raw TLS handshake to each Atlas shard from
inside the Cloud Run container and dump the result to stdout.

Targets the NEW GCP-hosted Flex cluster (kairocluster.h1uh059.mongodb.net).
If openssl handshake succeeds here, Cloud Run → Atlas network path is clean.
"""

from __future__ import annotations

import socket
import subprocess
import sys

SHARDS = [
    ("ac-rgeabgs-shard-00-00.h1uh059.mongodb.net", 27017),
    ("ac-rgeabgs-shard-00-01.h1uh059.mongodb.net", 27017),
    ("ac-rgeabgs-shard-00-02.h1uh059.mongodb.net", 27017),
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
            ["openssl", "s_client", "-connect", f"{host}:{port}",
             "-servername", host, tls_flag, "-brief"],
            input="", capture_output=True, text=True, timeout=15,
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
    _say("[TLS-DIAG] MongoDB Atlas (NEW GCP cluster) TLS handshake diagnostic")
    _say("[TLS-DIAG] Target: kairocluster.h1uh059.mongodb.net (Flex, GCP us-central1)")
    _say("=" * 70)

    try:
        ip = subprocess.run(
            ["curl", "-s", "--max-time", "5", "https://api.ipify.org"],
            capture_output=True, text=True, timeout=8,
        ).stdout.strip()
        _say(f"[TLS-DIAG] My egress IP (via api.ipify.org): {ip or '<empty>'}")
    except Exception as exc:  # noqa: BLE001
        _say(f"[TLS-DIAG] ipify check failed: {exc}")

    for host, port in SHARDS:
        _probe_dns(host)

    host, port = SHARDS[0]
    _probe_tls(host, port, "-tls1_2")
    _probe_tls(host, port, "-tls1_3")

    _say("\n" + "=" * 70)
    _say("[TLS-DIAG] Diagnostic complete — proceeding with Streamlit startup")
    _say("=" * 70 + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        _say(f"[TLS-DIAG] FATAL diagnostic error: {exc}")
    sys.exit(0)
