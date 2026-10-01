"""
Parse TLS ClientHello and compute JA3 / JA4 fingerprints.

Refs:
- JA3: https://github.com/salesforce/ja3
- JA4: https://github.com/FoxIO-LLC/ja4
"""

import socket
import struct
import hashlib
from typing import Optional


# GREASE values (RFC 8701)
GREASE_TABLE = {
    0x0a0a, 0x1a1a, 0x2a2a, 0x3a3a, 0x4a4a, 0x5a5a, 0x6a6a, 0x7a7a,
    0x8a8a, 0x9a9a, 0xaaaa, 0xbaba, 0xcaca, 0xdada, 0xeaea, 0xfafa,
}


def is_grease(value: int) -> bool:
    return value in GREASE_TABLE


def parse_client_hello(data: bytes) -> Optional[dict]:
    """
    Parse raw TLS ClientHello bytes into a structured dict.
    Returns None if the data is not a full ClientHello.
    """
    if len(data) < 9:
        return None

    # TLS record header
    if data[0] != 22:  # handshake
        return None
    record_len = struct.unpack('>H', data[3:5])[0]
    if len(data) < 5 + record_len:
        return None  # partial

    # Handshake header
    if data[5] != 1:  # client_hello
        return None
    hs_len = struct.unpack('>I', b'\x00' + data[6:9])[0]
    body = data[9:9 + hs_len]

    pos = 0

    # legacy_version
    legacy_version = struct.unpack('>H', body[pos:pos + 2])[0]
    pos += 2

    # random
    pos += 32

    # legacy_session_id
    sid_len = body[pos]
    pos += 1 + sid_len

    # cipher_suites
    cs_len = struct.unpack('>H', body[pos:pos + 2])[0]
    pos += 2
    cipher_suites = [
        struct.unpack('>H', body[pos + i:pos + i + 2])[0]
        for i in range(0, cs_len, 2)
    ]
    pos += cs_len

    # legacy_compression_methods
    comp_len = body[pos]
    pos += 1 + comp_len

    # extensions
    extensions = []
    if pos + 2 <= len(body):
        ext_total = struct.unpack('>H', body[pos:pos + 2])[0]
        pos += 2
        ext_end = pos + ext_total
        while pos + 4 <= ext_end:
            ext_type = struct.unpack('>H', body[pos:pos + 2])[0]
            ext_len = struct.unpack('>H', body[pos + 2:pos + 4])[0]
            ext_data = body[pos + 4:pos + 4 + ext_len]
            extensions.append({'type': ext_type, 'data': ext_data})
            pos += 4 + ext_len

    # Extract useful extensions
    sni = None
    alpn = []
    supported_groups = []
    ec_point_formats = []
    signature_algorithms = []
    supported_versions = []

    for ext in extensions:
        t, d = ext['type'], ext['data']

        if t == 0 and len(d) >= 5:  # server_name
            try:
                list_len = struct.unpack('>H', d[0:2])[0]
                p = 2
                while p < 2 + list_len:
                    name_type = d[p]
                    name_len = struct.unpack('>H', d[p + 1:p + 3])[0]
                    if name_type == 0:
                        sni = d[p + 3:p + 3 + name_len].decode('ascii', 'replace')
                        break
                    p += 3 + name_len
            except Exception:
                pass

        elif t == 16 and len(d) >= 2:  # ALPN
            try:
                list_len = struct.unpack('>H', d[0:2])[0]
                p = 2
                while p < 2 + list_len:
                    alpn_len = d[p]
                    alpn.append(d[p + 1:p + 1 + alpn_len].decode('ascii', 'replace'))
                    p += 1 + alpn_len
            except Exception:
                pass

        elif t == 10 and len(d) >= 2:  # supported_groups
            try:
                list_len = struct.unpack('>H', d[0:2])[0]
                for p in range(2, 2 + list_len, 2):
                    supported_groups.append(struct.unpack('>H', d[p:p + 2])[0])
            except Exception:
                pass

        elif t == 11 and len(d) >= 1:  # ec_point_formats
            try:
                list_len = d[0]
                ec_point_formats = list(d[1:1 + list_len])
            except Exception:
                pass

        elif t == 13 and len(d) >= 2:  # signature_algorithms
            try:
                list_len = struct.unpack('>H', d[0:2])[0]
                for p in range(2, 2 + list_len, 2):
                    signature_algorithms.append(struct.unpack('>H', d[p:p + 2])[0])
            except Exception:
                pass

        elif t == 43 and len(d) >= 1:  # supported_versions
            try:
                list_len = d[0]
                for p in range(1, 1 + list_len, 2):
                    supported_versions.append(struct.unpack('>H', d[p:p + 2])[0])
            except Exception:
                pass

    return {
        'legacy_version': legacy_version,
        'cipher_suites': cipher_suites,
        'extensions': extensions,
        'sni': sni,
        'alpn': alpn,
        'supported_groups': supported_groups,
        'ec_point_formats': ec_point_formats,
        'signature_algorithms': signature_algorithms,
        'supported_versions': supported_versions,
    }


def compute_ja3(ch: dict) -> tuple[str, str]:
    """Return (ja3_md5_hex, ja3_raw_string)."""
    version = ch['legacy_version']
    ciphers = [str(c) for c in ch['cipher_suites'] if not is_grease(c)]
    exts = [str(e['type']) for e in ch['extensions'] if not is_grease(e['type'])]
    curves = [str(c) for c in ch['supported_groups'] if not is_grease(c)]
    points = [str(p) for p in ch['ec_point_formats']]

    raw = ','.join([
        str(version),
        '-'.join(ciphers),
        '-'.join(exts),
        '-'.join(curves),
        '-'.join(points),
    ])
    return hashlib.md5(raw.encode()).hexdigest(), raw


def _tls_version_code(v: int) -> str:
    return {
        0x0304: '13',
        0x0303: '12',
        0x0302: '11',
        0x0301: '10',
        0x0300: 's3',
        0x0002: 's2',
    }.get(v, '00')


def _is_ip(s: str) -> bool:
    for fam in (socket.AF_INET, socket.AF_INET6):
        try:
            socket.inet_pton(fam, s)
            return True
        except (OSError, ValueError):
            pass
    return False


def compute_ja4(ch: dict) -> str:
    """
    Compute JA4 fingerprint (TCP variant).
    Format: JA4_a_JA4_b_JA4_c
    """
    # Highest supported TLS version
    if ch['supported_versions']:
        max_ver = max(ch['supported_versions'])
    else:
        max_ver = ch['legacy_version']
    ver_code = _tls_version_code(max_ver)

    # d = domain SNI, i = IP / no SNI
    sni = ch['sni']
    d_or_i = 'd' if (sni and not _is_ip(sni)) else 'i'

    ciphers_clean = [c for c in ch['cipher_suites'] if not is_grease(c)]
    c_count = min(len(ciphers_clean), 99)

    exts_clean = [e for e in ch['extensions'] if not is_grease(e['type'])]
    e_count = min(len(exts_clean), 99)

    # ALPN: first+last char of the first ALPN value, or "00"
    if ch['alpn']:
        a = ch['alpn'][0]
        alpn_code = (a[0] + a[-1]) if len(a) > 1 else (a + a)
    else:
        alpn_code = '00'

    ja4_a = f"t{ver_code}{d_or_i}{c_count:02d}{e_count:02d}{alpn_code}"

    ciphers_hex = sorted(f"{c:04x}" for c in ciphers_clean)
    ja4_b = hashlib.sha256(','.join(ciphers_hex).encode()).hexdigest()[:12]

    exts_hex = sorted(f"{e['type']:04x}" for e in exts_clean)
    sig_algs = sorted(f"{s:04x}" for s in ch['signature_algorithms'] if not is_grease(s))
    ja4_c = hashlib.sha256(
        (','.join(exts_hex) + '_' + ','.join(sig_algs)).encode()
    ).hexdigest()[:12]

    return f"{ja4_a}_{ja4_b}_{ja4_c}"
