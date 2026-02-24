"""
app/services/crypto.py

ActivityPub / HTTP Signatures crypto utilities.

- RSA-2048 key generation (PEM format)
- HTTP Signature signing (Mastodon-compatible, RSA-SHA256)
- HTTP Signature verification
- SHA-256 Digest header generation & validation
- Remote actor public-key fetching (with in-process cache)

Signing header order: (request-target) host date digest
Mastodon signature header format:
    Signature keyId="<key_id>",algorithm="rsa-sha256",headers="(request-target) host date digest",signature="<base64>"
"""

import base64
import hashlib
import re
import time
from datetime import datetime, timezone
from email.utils import formatdate
from functools import lru_cache
from typing import Optional
from urllib.parse import urlparse

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from cryptography.exceptions import InvalidSignature

# ---------------------------------------------------------------------------
# RSA Key Generation
# ---------------------------------------------------------------------------

def generate_rsa_keypair() -> tuple[str, str]:
    """
    Generate a fresh RSA-2048 key pair.

    Returns:
        (private_key_pem, public_key_pem) — both as UTF-8 strings in PEM format.
    """
    private_key: RSAPrivateKey = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    private_pem: str = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    public_pem: str = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    return private_pem, public_pem


# ---------------------------------------------------------------------------
# Digest Header
# ---------------------------------------------------------------------------

def sha256_digest(body: bytes) -> str:
    """
    Compute SHA-256 digest of *body* and return the value for the Digest header.

    Format: ``SHA-256=<base64-encoded-digest>``
    """
    digest_bytes = hashlib.sha256(body).digest()
    return "SHA-256=" + base64.b64encode(digest_bytes).decode("utf-8")


def verify_digest(body: bytes, digest_header: str) -> bool:
    """
    Verify the Digest header against *body*.  Returns True if valid.
    """
    if not digest_header.startswith("SHA-256="):
        return False
    expected = sha256_digest(body)
    return expected == digest_header.strip()


# ---------------------------------------------------------------------------
# HTTP Signature — Sign
# ---------------------------------------------------------------------------

_SIGNED_HEADERS = ("(request-target)", "host", "date", "digest")


def sign_request(
    method: str,
    url: str,
    body: bytes,
    private_key_pem: str,
    key_id: str,
) -> dict[str, str]:
    """
    Sign an outgoing HTTP request per the HTTP Signatures spec (draft-cavage-http-signatures).

    Args:
        method:          HTTP method in *lowercase* (e.g. "post")
        url:             Full target URL string
        body:            Raw request body bytes
        private_key_pem: PEM-encoded RSA private key (PKCS#8 / PKCS#1)
        key_id:          The ``keyId`` value (e.g. ``https://example.com/users/alice#main-key``)

    Returns:
        A dict of headers to merge into the outgoing request:
        ``{"Host": ..., "Date": ..., "Digest": ..., "Signature": ...}``
    """
    parsed = urlparse(url)
    host = parsed.netloc
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    date = formatdate(usegmt=True)
    digest = sha256_digest(body)
    request_target = f"{method.lower()} {path}"

    # Build the string to sign — order MUST match _SIGNED_HEADERS
    signing_string = "\n".join([
        f"(request-target): {request_target}",
        f"host: {host}",
        f"date: {date}",
        f"digest: {digest}",
    ])

    # Load private key (supports PKCS#8 and PKCS#1)
    private_key: RSAPrivateKey = serialization.load_pem_private_key(
        private_key_pem.encode("utf-8"),
        password=None,
    )  # type: ignore[assignment]

    raw_signature = private_key.sign(
        signing_string.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )

    signature_b64 = base64.b64encode(raw_signature).decode("utf-8")
    headers_list = " ".join(_SIGNED_HEADERS)

    signature_header = (
        f'keyId="{key_id}",'
        f'algorithm="rsa-sha256",'
        f'headers="{headers_list}",'
        f'signature="{signature_b64}"'
    )

    return {
        "Host": host,
        "Date": date,
        "Digest": digest,
        "Signature": signature_header,
        "Content-Type": "application/activity+json",
    }


# ---------------------------------------------------------------------------
# HTTP Signature — Verify
# ---------------------------------------------------------------------------

_SIG_RE = re.compile(r'(\w+)="([^"]*)"')


def _parse_signature_header(header: str) -> dict[str, str]:
    return dict(_SIG_RE.findall(header))


def verify_signature(
    method: str,
    path: str,
    headers: dict[str, str],
    body: bytes,
    public_key_pem: str,
) -> bool:
    """
    Verify an HTTP Signature on an incoming request.

    Args:
        method:         HTTP method (lowercase)
        path:           Request path (with query string if present)
        headers:        Dict of *lowercase* header names → values
        body:           Raw request body bytes
        public_key_pem: PEM-encoded RSA public key

    Returns:
        True if the signature is valid, False otherwise.
    """
    sig_header = headers.get("signature") or headers.get("Signature")
    if not sig_header:
        return False

    parts = _parse_signature_header(sig_header)
    signed_headers_str = parts.get("headers", "date")
    signature_b64 = parts.get("signature", "")
    if not signature_b64:
        return False

    # Reconstruct the signing string from the header order in the Signature header
    signing_lines = []
    for h in signed_headers_str.split():
        if h == "(request-target)":
            signing_lines.append(f"(request-target): {method.lower()} {path}")
        else:
            value = headers.get(h) or headers.get(h.title()) or headers.get(h.upper())
            if value is None:
                return False
            signing_lines.append(f"{h}: {value}")

    signing_string = "\n".join(signing_lines)

    try:
        public_key: RSAPublicKey = serialization.load_pem_public_key(
            public_key_pem.encode("utf-8"),
        )  # type: ignore[assignment]
        public_key.verify(
            base64.b64decode(signature_b64),
            signing_string.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except (InvalidSignature, Exception):
        return False


# ---------------------------------------------------------------------------
# Remote Public Key Fetching
# ---------------------------------------------------------------------------

# Simple in-process cache:  key_id → (public_key_pem, fetched_at)
_pubkey_cache: dict[str, tuple[str, float]] = {}
_CACHE_TTL = 3600  # seconds


def fetch_remote_public_key(key_id: str, actor_url: Optional[str] = None) -> Optional[str]:
    """
    Fetch the RSA public key PEM for a remote actor.

    First checks an in-process cache (TTL = 1 hour).
    If *key_id* ends with ``#main-key`` the actor URL is derived by stripping the fragment.

    Args:
        key_id:    The ``keyId`` from the Signature header
        actor_url: Optional explicit actor URL (overrides derivation from key_id)

    Returns:
        PEM-encoded public key string, or None on failure.
    """
    # Cache hit
    if key_id in _pubkey_cache:
        pem, fetched_at = _pubkey_cache[key_id]
        if time.time() - fetched_at < _CACHE_TTL:
            return pem

    # Derive actor URL
    url = actor_url or key_id.split("#")[0]

    try:
        resp = httpx.get(
            url,
            headers={"Accept": "application/activity+json"},
            timeout=10,
            follow_redirects=True,
        )
        resp.raise_for_status()
        actor_doc = resp.json()

        public_key_section = actor_doc.get("publicKey") or {}
        pem = public_key_section.get("publicKeyPem") or actor_doc.get("publicKeyPem")
        if not pem:
            return None

        _pubkey_cache[key_id] = (pem, time.time())
        return pem

    except Exception:
        return None
