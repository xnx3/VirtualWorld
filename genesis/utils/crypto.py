"""Cryptographic utilities: Ed25519 keys, signing, hashing, Merkle trees, key encryption."""

from __future__ import annotations

import hashlib
import os
import struct

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes, serialization


# ---------------------------------------------------------------------------
# Ed25519 key-pair helpers
# ---------------------------------------------------------------------------

def generate_keypair() -> tuple[bytes, bytes]:
    """Generate an Ed25519 key pair.

    Returns:
        (private_key_bytes, public_key_bytes) -- both as raw 32-byte values.
    """
    private_key = Ed25519PrivateKey.generate()
    priv_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return priv_bytes, pub_bytes


def public_key_from_private_key(private_key_bytes: bytes) -> bytes:
    """Derive the raw Ed25519 public key bytes from a raw private key."""
    private_key = _load_private_key(private_key_bytes)
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _load_private_key(private_key_bytes: bytes) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(private_key_bytes)


def _load_public_key(public_key_bytes: bytes) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(public_key_bytes)


# ---------------------------------------------------------------------------
# Signing / verification
# ---------------------------------------------------------------------------

def sign(private_key_bytes: bytes, data: bytes) -> bytes:
    """Sign *data* with an Ed25519 private key and return the 64-byte signature."""
    key = _load_private_key(private_key_bytes)
    return key.sign(data)


def verify(public_key_bytes: bytes, data: bytes, signature_bytes: bytes) -> bool:
    """Verify an Ed25519 signature.  Returns ``True`` on success, ``False`` on failure."""
    try:
        key = _load_public_key(public_key_bytes)
        key.verify(signature_bytes, data)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def sha256(data: bytes) -> str:
    """Return the SHA-256 hex digest of *data*."""
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Merkle tree
# ---------------------------------------------------------------------------

def _hash_pair(a: str, b: str) -> str:
    """Hash two hex-encoded hashes together (sorted for determinism)."""
    combined = min(a, b) + max(a, b)
    return hashlib.sha256(combined.encode()).hexdigest()


def merkle_root(hashes: list[str]) -> str:
    """Compute the Merkle root of a list of hex-encoded hashes.

    If the list is empty, returns the SHA-256 of the empty byte-string.
    If odd, the last element is duplicated.
    """
    if not hashes:
        return sha256(b"")

    layer = list(hashes)
    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])
        next_layer: list[str] = []
        for i in range(0, len(layer), 2):
            next_layer.append(_hash_pair(layer[i], layer[i + 1]))
        layer = next_layer
    return layer[0]


# ---------------------------------------------------------------------------
# Private-key encryption (AES-256-GCM + PBKDF2)
# ---------------------------------------------------------------------------

_KDF_ITERATIONS = 480_000
_SALT_LEN = 16
_NONCE_LEN = 12  # 96-bit nonce for AES-GCM

# On-disk format: salt (16) || nonce (12) || ciphertext+tag (variable)


def _derive_aes_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_KDF_ITERATIONS,
    )
    return kdf.derive(password.encode())


def encrypt_private_key(private_key_bytes: bytes, password: str) -> bytes:
    """Encrypt a raw private key with *password* using AES-256-GCM + PBKDF2.

    Returns the concatenation ``salt || nonce || ciphertext+tag``.
    """
    salt = os.urandom(_SALT_LEN)
    nonce = os.urandom(_NONCE_LEN)
    aes_key = _derive_aes_key(password, salt)
    aesgcm = AESGCM(aes_key)
    ct = aesgcm.encrypt(nonce, private_key_bytes, None)
    return salt + nonce + ct


def decrypt_private_key(encrypted_bytes: bytes, password: str) -> bytes:
    """Decrypt an encrypted private key produced by :func:`encrypt_private_key`.

    Raises ``ValueError`` on wrong password or corrupted data.
    """
    if len(encrypted_bytes) < _SALT_LEN + _NONCE_LEN + 1:
        raise ValueError("Encrypted data too short")

    salt = encrypted_bytes[:_SALT_LEN]
    nonce = encrypted_bytes[_SALT_LEN : _SALT_LEN + _NONCE_LEN]
    ct = encrypted_bytes[_SALT_LEN + _NONCE_LEN :]

    aes_key = _derive_aes_key(password, salt)
    aesgcm = AESGCM(aes_key)
    try:
        return aesgcm.decrypt(nonce, ct, None)
    except Exception as exc:
        raise ValueError("Decryption failed (wrong password or corrupted data)") from exc


# ---------------------------------------------------------------------------
# Node ID derivation
# ---------------------------------------------------------------------------

def node_id_from_public_key(public_key_bytes: bytes) -> str:
    """Derive a deterministic node ID from a raw Ed25519 public key.

    The ID is the full SHA-256 hex digest of the public key bytes.
    """
    return hashlib.sha256(public_key_bytes).hexdigest()
