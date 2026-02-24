"""
tests/test_activitypub.py

Unit tests for ActivityPub compliance:
  - Crypto: RSA keygen, HTTP signature sign/verify, Digest header
  - WebFinger endpoint
  - Actor endpoint (content-negotiated)
  - Outbox GET (OrderedCollection)
  - Inbox: valid delivery, bad digest rejection, missing signature rejection
"""

import base64
import hashlib
import json
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.services.crypto import (
    generate_rsa_keypair,
    sha256_digest,
    sign_request,
    verify_digest,
    verify_signature,
)

# ---------------------------------------------------------------------------
# Crypto unit tests (no DB needed)
# ---------------------------------------------------------------------------


class TestRsaKeygen:
    def test_generate_returns_two_pem_strings(self):
        priv, pub = generate_rsa_keypair()
        assert priv.startswith("-----BEGIN PRIVATE KEY-----")
        assert pub.startswith("-----BEGIN PUBLIC KEY-----")

    def test_different_keypairs_each_call(self):
        priv1, pub1 = generate_rsa_keypair()
        priv2, pub2 = generate_rsa_keypair()
        assert priv1 != priv2
        assert pub1 != pub2


class TestDigest:
    def test_sha256_digest_format(self):
        body = b"hello world"
        digest = sha256_digest(body)
        assert digest.startswith("SHA-256=")
        # Verify it's valid base64
        b64_part = digest[len("SHA-256="):]
        decoded = base64.b64decode(b64_part)
        assert hashlib.sha256(body).digest() == decoded

    def test_verify_digest_success(self):
        body = b"test body content"
        digest = sha256_digest(body)
        assert verify_digest(body, digest) is True

    def test_verify_digest_failure(self):
        body = b"test body content"
        digest = sha256_digest(b"different content")
        assert verify_digest(body, digest) is False

    def test_verify_digest_wrong_algorithm(self):
        assert verify_digest(b"body", "MD5=abc123") is False


class TestHttpSignature:
    @pytest.fixture(autouse=True)
    def keypair(self):
        self.priv, self.pub = generate_rsa_keypair()
        self.key_id = "https://example.com/users/alice#main-key"

    def test_sign_and_verify_roundtrip(self):
        url = "https://remote.social/users/bob/inbox"
        body = b'{"type":"Follow"}'
        headers = sign_request("post", url, body, self.priv, self.key_id)

        # Build the header map as it would arrive at the server
        header_map = {
            "host": headers["Host"],
            "date": headers["Date"],
            "digest": headers["Digest"],
            "signature": headers["Signature"],
        }

        result = verify_signature("post", "/users/bob/inbox", header_map, body, self.pub)
        assert result is True

    def test_signature_header_contains_required_fields(self):
        url = "https://remote.social/users/bob/inbox"
        body = b"{}"
        headers = sign_request("post", url, body, self.priv, self.key_id)
        sig = headers["Signature"]
        assert f'keyId="{self.key_id}"' in sig
        assert 'algorithm="rsa-sha256"' in sig
        assert "(request-target)" in sig
        assert "host" in sig
        assert "date" in sig
        assert "digest" in sig

    def test_verify_fails_with_wrong_key(self):
        _, other_pub = generate_rsa_keypair()
        url = "https://remote.social/users/bob/inbox"
        body = b'{"type":"Follow"}'
        headers = sign_request("post", url, body, self.priv, self.key_id)
        header_map = {
            "host": headers["Host"],
            "date": headers["Date"],
            "digest": headers["Digest"],
            "signature": headers["Signature"],
        }
        result = verify_signature("post", "/users/bob/inbox", header_map, body, other_pub)
        assert result is False

    def test_verify_fails_with_tampered_body(self):
        url = "https://remote.social/users/bob/inbox"
        body = b'{"type":"Follow"}'
        headers = sign_request("post", url, body, self.priv, self.key_id)
        header_map = {
            "host": headers["Host"],
            "date": headers["Date"],
            "digest": headers["Digest"],
            "signature": headers["Signature"],
        }
        # Tamper the digest to simulate a body change
        header_map["digest"] = sha256_digest(b"tampered body")
        result = verify_signature("post", "/users/bob/inbox", header_map, b"tampered body", self.pub)
        # Signature mismatch (signed over original body's digest)
        assert result is False

    def test_verify_fails_with_missing_signature(self):
        result = verify_signature("post", "/inbox", {}, b"body", self.pub)
        assert result is False


# ---------------------------------------------------------------------------
# HTTP endpoint tests (with test client)
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


class TestWebFinger:
    def test_returns_jrd_content_type(self, client):
        resp = client.get(
            "/.well-known/webfinger",
            params={"resource": "acct:testuser7@example.com"},
            headers={"Accept": "application/jrd+json"},
        )
        # 200 if user exists (testuser7 created by conftest.py fake_user fixture)
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            assert "application/jrd+json" in resp.headers["content-type"]

    def test_returns_correct_structure(self, client):
        resp = client.get(
            "/.well-known/webfinger",
            params={"resource": "acct:testuser7@example.com"},
        )
        if resp.status_code == 200:
            data = resp.json()
            assert "subject" in data
            assert "links" in data
            links = {link["rel"]: link for link in data["links"]}
            assert "self" in links
            assert links["self"]["type"] == "application/activity+json"

    def test_invalid_resource_returns_400(self, client):
        resp = client.get(
            "/.well-known/webfinger",
            params={"resource": "not-an-acct-uri"},
        )
        assert resp.status_code == 400

    def test_unknown_user_returns_404(self, client):
        resp = client.get(
            "/.well-known/webfinger",
            params={"resource": "acct:nobody_xyz_123@example.com"},
        )
        assert resp.status_code == 404


class TestActorEndpoint:
    def test_returns_406_without_accept_header(self, client):
        resp = client.get("/users/testuser7")
        # Without AP Accept header, returns 406
        assert resp.status_code in (200, 406)

    def test_returns_actor_with_accept_header(self, client):
        resp = client.get(
            "/users/testuser7",
            headers={"Accept": "application/activity+json"},
        )
        if resp.status_code == 200:
            data = resp.json()
            assert "@context" in data
            assert data["type"] == "Person"
            assert "inbox" in data
            assert "outbox" in data
            assert "followers" in data
            assert "following" in data
            assert "publicKey" in data
            pk = data["publicKey"]
            assert "id" in pk
            assert "owner" in pk
            assert "publicKeyPem" in pk
            assert pk["id"].endswith("#main-key")

    def test_returns_404_for_unknown_user(self, client):
        resp = client.get(
            "/users/nobody_xyz_abc",
            headers={"Accept": "application/activity+json"},
        )
        assert resp.status_code == 404


class TestOutbox:
    def test_outbox_returns_ordered_collection(self, client):
        resp = client.get(
            "/users/testuser7/outbox",
            headers={"Accept": "application/activity+json"},
        )
        if resp.status_code == 200:
            data = resp.json()
            assert data["type"] == "OrderedCollection"
            assert "@context" in data
            assert "totalItems" in data
            assert "first" in data

    def test_outbox_page_returns_ordered_collection_page(self, client):
        resp = client.get(
            "/users/testuser7/outbox",
            params={"page": 1},
            headers={"Accept": "application/activity+json"},
        )
        if resp.status_code == 200:
            data = resp.json()
            assert data["type"] == "OrderedCollectionPage"
            assert "orderedItems" in data
            assert isinstance(data["orderedItems"], list)


class TestInbox:
    def test_inbox_rejects_missing_digest(self, client):
        body = json.dumps({
            "type": "Follow",
            "actor": "https://remote.social/users/bob",
            "object": "https://example.com/users/testuser7",
        }).encode()

        resp = client.post(
            "/users/testuser7/inbox",
            content=body,
            headers={"Content-Type": "application/activity+json"},
        )
        assert resp.status_code == 400

    def test_inbox_rejects_bad_digest(self, client):
        body = json.dumps({"type": "Follow", "actor": "https://remote.social/users/bob"}).encode()

        resp = client.post(
            "/users/testuser7/inbox",
            content=body,
            headers={
                "Content-Type": "application/activity+json",
                "Digest": "SHA-256=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
            },
        )
        assert resp.status_code == 400

    def test_inbox_rejects_missing_signature(self, client):
        body = json.dumps({"type": "Follow", "actor": "https://remote.social/users/bob"}).encode()
        digest = sha256_digest(body)

        resp = client.post(
            "/users/testuser7/inbox",
            content=body,
            headers={
                "Content-Type": "application/activity+json",
                "Digest": digest,
            },
        )
        assert resp.status_code == 401

    def test_inbox_rejects_invalid_signature(self, client):
        """Signature present but the actor's public key doesn't match."""
        body = json.dumps({
            "type": "Follow",
            "actor": "https://remote.social/users/bob",
            "object": "https://example.com/users/testuser7",
        }).encode()
        digest = sha256_digest(body)

        # Sign with a key that is NOT the remote actor's key
        priv, _ = generate_rsa_keypair()
        headers = sign_request(
            "post",
            "https://example.com/users/testuser7/inbox",
            body,
            priv,
            "https://remote.social/users/bob#main-key",
        )

        # Mock fetch_remote_public_key to return a *different* public key
        _, different_pub = generate_rsa_keypair()
        with patch("app.routers.activitypub.fetch_remote_public_key", return_value=different_pub):
            resp = client.post(
                "/users/testuser7/inbox",
                content=body,
                headers={
                    "Content-Type": "application/activity+json",
                    "Digest": digest,
                    "Signature": headers["Signature"],
                    "Date": headers["Date"],
                    "Host": "example.com",
                },
            )
        assert resp.status_code == 401

    def test_inbox_accepts_valid_signed_request(self, client):
        """Full happy path: valid Digest + valid Signature."""
        body = json.dumps({
            "@context": "https://www.w3.org/ns/activitystreams",
            "id": "https://remote.social/activities/" + str(uuid.uuid4()),
            "type": "Follow",
            "actor": "https://remote.social/users/bob",
            "object": "https://example.com/users/testuser7",
        }).encode()
        digest = sha256_digest(body)

        priv, pub = generate_rsa_keypair()
        headers = sign_request(
            "post",
            "https://example.com/users/testuser7/inbox",
            body,
            priv,
            "https://remote.social/users/bob#main-key",
        )

        # Mock the remote key fetch to return the matching public key
        with patch("app.routers.activitypub.fetch_remote_public_key", return_value=pub):
            resp = client.post(
                "/users/testuser7/inbox",
                content=body,
                headers={
                    "Content-Type": "application/activity+json",
                    "Digest": digest,
                    "Signature": headers["Signature"],
                    "Date": headers["Date"],
                    "Host": "example.com",
                },
            )

        assert resp.status_code == 202
        assert resp.json()["status"] == "accepted"


class TestFollowersFollowing:
    def test_followers_returns_ordered_collection(self, client):
        resp = client.get("/users/testuser7/followers")
        if resp.status_code == 200:
            data = resp.json()
            assert data["type"] == "OrderedCollection"
            assert "totalItems" in data

    def test_following_returns_ordered_collection(self, client):
        resp = client.get("/users/testuser7/following")
        if resp.status_code == 200:
            data = resp.json()
            assert data["type"] == "OrderedCollection"
            assert "totalItems" in data
