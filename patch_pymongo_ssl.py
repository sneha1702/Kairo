#!/usr/bin/env python3
"""
Build-time patch: force TLS 1.2-only SSLContext in pymongo's ssl_support.

Atlas M0 rejects certain TLS handshakes from Cloud Run.
Replacing PROTOCOL_SSLv23 with PROTOCOL_TLSv1_2 at context creation time is
more definitive than maximum_version — it tells OpenSSL to create a TLS 1.2-only
context rather than a general TLS context capped post-hoc.

Works with both pymongo 3.x (_ssl prefix) and pymongo 4.x (ssl prefix).
"""
import pathlib
import pymongo.ssl_support as _m

p = pathlib.Path(_m.__file__)
code = p.read_text()

# Each tuple: (line to find, replacement)
# pymongo 3.x uses _ssl as the ssl module; 4.x uses ssl (local var = _stdlibssl)
REPLACEMENTS = [
    (
        "        ctx = _ssl.SSLContext(_ssl.PROTOCOL_SSLv23)",
        "        ctx = _ssl.SSLContext(getattr(_ssl, 'PROTOCOL_TLSv1_2', _ssl.PROTOCOL_SSLv23))",
    ),
    (
        "        ctx = ssl.SSLContext(ssl.PROTOCOL_SSLv23)",
        "        ctx = ssl.SSLContext(getattr(_stdlibssl, 'PROTOCOL_TLSv1_2', ssl.PROTOCOL_SSLv23))",
    ),
]

matched = False
for old, new in REPLACEMENTS:
    if old in code:
        code = code.replace(old, new, 1)
        matched = True
        print(f"[patch_pymongo_ssl] Patched {p}")
        print(f"  replaced: {old.strip()!r}")
        print(f"  with:     {new.strip()!r}")
        break

if not matched:
    print(f"[patch_pymongo_ssl] No target found in {p} — skipping")
    raise SystemExit(0)

p.write_text(code)
