"""
RSA key management and HTTP Signature utilities for ActivityPub federation.
"""

import base64
import hashlib
import datetime
from urllib.parse import urlparse

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding


def generate_rsa_keypair() -> tuple[str, str]:
    """Generate an RSA keypair and return (private_key_pem, public_key_pem) as strings."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    return private_pem, public_pem


def sign_request(
    private_key_pem: str,
    method: str,
    url: str,
    body: bytes | None,
    key_id: str,
) -> dict[str, str]:
    """
    Generate HTTP Signature headers for an outgoing request.

    Returns a dict of headers to merge into the request:
      - Date
      - Digest (if body present)
      - Signature
      - Content-Type (application/activity+json)
    """
    parsed = urlparse(url)
    host = parsed.hostname
    if parsed.port and parsed.port not in (80, 443):
        host = f"{host}:{parsed.port}"
    path = parsed.path

    now = datetime.datetime.utcnow()
    date_str = now.strftime("%a, %d %b %Y %H:%M:%S GMT")

    headers_to_sign = ["(request-target)", "host", "date"]
    signed_parts = [
        f"(request-target): {method.lower()} {path}",
        f"host: {host}",
        f"date: {date_str}",
    ]

    result_headers = {
        "Host": host,
        "Date": date_str,
        "Content-Type": "application/activity+json",
    }

    if body:
        digest = base64.b64encode(hashlib.sha256(body).digest()).decode("utf-8")
        digest_header = f"SHA-256={digest}"
        headers_to_sign.append("digest")
        signed_parts.append(f"digest: {digest_header}")
        result_headers["Digest"] = digest_header

    signing_string = "\n".join(signed_parts)

    private_key = serialization.load_pem_private_key(
        private_key_pem.encode("utf-8"), password=None
    )

    signature_bytes = private_key.sign(
        signing_string.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )

    sig_b64 = base64.b64encode(signature_bytes).decode("utf-8")

    sig_header = (
        f'keyId="{key_id}",'
        f'algorithm="rsa-sha256",'
        f'headers="{" ".join(headers_to_sign)}",'
        f'signature="{sig_b64}"'
    )

    result_headers["Signature"] = sig_header

    return result_headers


def verify_http_signature(
    method: str,
    path: str,
    headers: dict[str, str],
    public_key_pem: str,
) -> bool:
    """
    Verify an HTTP Signature on an incoming request.
    Returns True if valid, False otherwise.
    """
    try:
        sig_header = headers.get("signature", headers.get("Signature", ""))
        if not sig_header:
            return False

        # Parse signature header
        sig_parts = {}
        for part in sig_header.split(","):
            key, _, value = part.strip().partition("=")
            sig_parts[key.strip()] = value.strip().strip('"')

        signed_headers = sig_parts.get("headers", "date").split(" ")
        signature = base64.b64decode(sig_parts.get("signature", ""))

        # Reconstruct signing string
        signing_parts = []
        for h in signed_headers:
            if h == "(request-target)":
                signing_parts.append(
                    f"(request-target): {method.lower()} {path}"
                )
            else:
                # Case-insensitive header lookup
                value = None
                for k, v in headers.items():
                    if k.lower() == h.lower():
                        value = v
                        break
                if value is None:
                    return False
                signing_parts.append(f"{h}: {value}")

        signing_string = "\n".join(signing_parts)

        public_key = serialization.load_pem_public_key(
            public_key_pem.encode("utf-8")
        )

        public_key.verify(
            signature,
            signing_string.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )

        return True

    except Exception:
        return False
