"""
TLS server that inspects ClientHello and returns JA3/JA4 fingerprint.
Runs as a standalone process, not as a FastAPI route.
"""

import socket
import ssl
import json
import struct
import logging
import threading
import time
from datetime import datetime, timezone

from .parser import (
    parse_client_hello, compute_ja3, compute_ja4, is_grease,
)

logger = logging.getLogger(__name__)


class FingerprintServer:
    def __init__(self, host: str, port: int, certfile: str, keyfile: str):
        self.host = host
        self.port = port
        self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ssl_context.load_cert_chain(certfile, keyfile)
        self.ssl_context.verify_mode = ssl.CERT_NONE

    def serve_forever(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.listen(64)
        logger.info(f"Fingerprint server listening on {self.host}:{self.port}")
        try:
            while True:
                try:
                    conn, addr = sock.accept()
                except OSError:
                    break
                t = threading.Thread(
                    target=self._handle, args=(conn, addr), daemon=True,
                )
                t.start()
        finally:
            sock.close()

    def _handle(self, conn, addr):
        try:
            conn.settimeout(10)

            # Peek at the ClientHello bytes without consuming them.
            # TLS ClientHello typically arrives in one TCP segment.
            peek = b''
            try:
                peek = conn.recv(16384, socket.MSG_PEEK)
            except (socket.timeout, BlockingIOError):
                pass

            ch = parse_client_hello(peek) if peek else None
            if ch is None:
                logger.warning(f"Could not parse ClientHello from {addr[0]}")

            # Complete TLS handshake — this consumes the ClientHello
            ssl_conn = self.ssl_context.wrap_socket(conn, server_side=True)

            # Read HTTP request headers
            request = b''
            while b'\r\n\r\n' not in request:
                chunk = ssl_conn.recv(4096)
                if not chunk:
                    break
                request += chunk
                if len(request) > 16384:
                    break

            first_line = request.split(b'\r\n', 1)[0].decode('utf-8', 'replace')
            parts = first_line.split(' ')
            method = parts[0] if parts else 'GET'
            path = parts[1] if len(parts) > 1 else '/'

            if method == 'OPTIONS':
                response = self._cors_preflight()
            elif path == '/health':
                response = self._json_response({'status': 'ok'})
            elif path.startswith('/api/fingerprint') or path == '/':
                response = self._json_response(self._fingerprint_data(ch, addr))
            else:
                response = self._not_found()

            ssl_conn.sendall(response)
            try:
                ssl_conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            ssl_conn.close()

        except ssl.SSLError as e:
            logger.warning(f"TLS error from {addr[0]}: {e}")
            try: conn.close()
            except Exception: pass
        except Exception as e:
            logger.exception(f"Error handling {addr[0]}: {e}")
            try: conn.close()
            except Exception: pass

    def _fingerprint_data(self, ch, addr):
        if not ch:
            return {'error': 'ClientHello not parsed'}

        try:
            ja3_hash, ja3_raw = compute_ja3(ch)
        except Exception as e:
            logger.warning(f"JA3 failed: {e}")
            ja3_hash, ja3_raw = '', ''

        try:
            ja4 = compute_ja4(ch)
        except Exception as e:
            logger.warning(f"JA4 failed: {e}")
            ja4 = ''

        return {
            'ip': addr[0],
            'ja3_hash': ja3_hash,
            'ja3_raw': ja3_raw,
            'ja4': ja4,
            'sni': ch.get('sni'),
            'alpn': ch.get('alpn', []),
            'cipher_count': len([c for c in ch['cipher_suites'] if not is_grease(c)]),
            'ext_count': len([e for e in ch['extensions'] if not is_grease(e['type'])]),
            'tls_version': ch.get('legacy_version'),
            'server_seen_at': datetime.now(timezone.utc).isoformat(),
        }

    def _json_response(self, data: dict) -> bytes:
        body = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
        headers = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json; charset=utf-8\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Access-Control-Allow-Methods: GET, OPTIONS\r\n"
            "Access-Control-Allow-Headers: Content-Type\r\n"
            "Cache-Control: no-store\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode('ascii')
        return headers + body

    def _cors_preflight(self) -> bytes:
        return (
            "HTTP/1.1 204 No Content\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Access-Control-Allow-Methods: GET, OPTIONS\r\n"
            "Access-Control-Allow-Headers: Content-Type\r\n"
            "Access-Control-Max-Age: 86400\r\n"
            "Content-Length: 0\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode('ascii')

    def _not_found(self) -> bytes:
        body = b'{"error":"not found"}'
        return (
            "HTTP/1.1 404 Not Found\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode('ascii') + body
