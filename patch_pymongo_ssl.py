#!/usr/bin/env python3
"""
Build-time patch: force TLS 1.2 max in pymongo's ssl_support.get_ssl_context.

Atlas M0 (free tier) sends TLSV1_ALERT_INTERNAL_ERROR when the TLS 1.3
ClientHello arrives from Cloud Run's network stack. Capping the SSL context
at TLS 1.2 avoids the extension that triggers the rejection.

Run once after `poetry install` during Docker image build.
"""
import pathlib
import pymongo.ssl_support as _m

p = pathlib.Path(_m.__file__)
code = p.read_text()

TARGET = '            ctx.options |= ssl.OP_NO_RENEGOTIATION'

if TARGET not in code:
    print(f"[patch_pymongo_ssl] Target line not found in {p} — already patched or layout changed")
    raise SystemExit(0)

ADDITION = (
    "\n"
    "        # Force TLS 1.2 max: Atlas M0 rejects TLS 1.3 from Cloud Run\n"
    '        if hasattr(_stdlibssl, "TLSVersion"):\n'
    "            try:\n"
    "                ctx.maximum_version = _stdlibssl.TLSVersion.TLSv1_2\n"
    "            except Exception:\n"
    '                if hasattr(_stdlibssl, "OP_NO_TLSv1_3"):\n'
    "                    ctx.options |= _stdlibssl.OP_NO_TLSv1_3\n"
)

p.write_text(code.replace(TARGET, TARGET + ADDITION, 1))
print(f"[patch_pymongo_ssl] Patched {p}")
