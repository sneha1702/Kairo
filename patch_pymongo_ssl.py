#!/usr/bin/env python3
"""
Build-time patch: force TLS 1.2 max in pymongo's ssl_support.get_ssl_context.

Atlas M0 rejects certain TLS ClientHellos from Cloud Run.
Capping at TLS 1.2 avoids the extension that triggers the rejection.

Handles both pymongo 3.x (_ssl prefix) and pymongo 4.x (ssl / _stdlibssl prefix).
"""
import pathlib
import pymongo.ssl_support as _m

p = pathlib.Path(_m.__file__)
code = p.read_text()

# (target_line, ssl_var_name_in_that_file)
# pymongo 3.x imports ssl as `_ssl`; 4.x exposes it as `_stdlibssl`
CANDIDATES = [
    ('            ctx.options |= _ssl.OP_NO_RENEGOTIATION',  '_ssl'),       # pymongo 3.x
    ('            ctx.options |= ssl.OP_NO_RENEGOTIATION',   '_stdlibssl'), # pymongo 4.x
    ('            ctx.options |= _ssl.OP_NO_COMPRESSION',    '_ssl'),       # 3.x fallback
    ('            ctx.options |= ssl.OP_NO_COMPRESSION',     '_stdlibssl'), # 4.x fallback
]

match = next(((t, v) for t, v in CANDIDATES if t in code), None)
if match is None:
    print(f"[patch_pymongo_ssl] No known target line found in {p} — skipping")
    raise SystemExit(0)

target, ssl_var = match

ADDITION = (
    "\n"
    "        # Force TLS 1.2 max: Atlas M0 rejects certain TLS handshakes from Cloud Run\n"
    f'        if hasattr({ssl_var}, "TLSVersion"):\n'
    "            try:\n"
    f"                ctx.maximum_version = {ssl_var}.TLSVersion.TLSv1_2\n"
    "            except Exception:\n"
    f'                if hasattr({ssl_var}, "OP_NO_TLSv1_3"):\n'
    f"                    ctx.options |= {ssl_var}.OP_NO_TLSv1_3\n"
)

p.write_text(code.replace(target, target + ADDITION, 1))
print(f"[patch_pymongo_ssl] Patched {p} (target: {target.strip()!r}, ssl_var: {ssl_var})")
