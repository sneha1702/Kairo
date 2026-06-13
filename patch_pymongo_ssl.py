#!/usr/bin/env python3
"""
Build-time patch: force TLS 1.2 max in pymongo's ssl_support.get_ssl_context.

Atlas M0 rejects certain TLS ClientHellos from Cloud Run.
Capping at TLS 1.2 avoids the extension that triggers the rejection.

Works with both pymongo 3.x and 4.x.
"""
import pathlib
import pymongo.ssl_support as _m

p = pathlib.Path(_m.__file__)
code = p.read_text()

# Try 4.x target first (has OP_NO_RENEGOTIATION), then fall back to 3.x
TARGETS = [
    '            ctx.options |= ssl.OP_NO_RENEGOTIATION',
    '            ctx.options |= ssl.OP_NO_COMPRESSION',
]

target = next((t for t in TARGETS if t in code), None)
if target is None:
    print(f"[patch_pymongo_ssl] No known target line found in {p} — skipping")
    raise SystemExit(0)

ADDITION = (
    "\n"
    "        # Force TLS 1.2 max: Atlas M0 rejects certain TLS handshakes from Cloud Run\n"
    '        if hasattr(_stdlibssl, "TLSVersion"):\n'
    "            try:\n"
    "                ctx.maximum_version = _stdlibssl.TLSVersion.TLSv1_2\n"
    "            except Exception:\n"
    '                if hasattr(_stdlibssl, "OP_NO_TLSv1_3"):\n'
    "                    ctx.options |= _stdlibssl.OP_NO_TLSv1_3\n"
)

p.write_text(code.replace(target, target + ADDITION, 1))
print(f"[patch_pymongo_ssl] Patched {p} (target: {target.strip()})")
