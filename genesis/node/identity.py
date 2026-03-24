"""Node identity management backed by Ed25519 key pairs.

Each node has a persistent identity consisting of a key pair stored on disk.
The private key may optionally be encrypted with a password.
"""

from __future__ import annotations

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from genesis.utils.crypto import (
    decrypt_private_key,
    encrypt_private_key,
    generate_keypair,
    node_id_from_public_key,
)


_IDENTITY_FILE = "identity.key"

# On-disk format:
#   byte 0:  flags  (0x00 = plaintext, 0x01 = encrypted)
#   bytes 1-32: public key  (32 bytes)
#   bytes 33+:  private key payload
#       plaintext  -> raw 32 bytes
#       encrypted  -> output of encrypt_private_key()

_FLAG_PLAIN: int = 0x00
_FLAG_ENCRYPTED: int = 0x01


@dataclass(frozen=True)
class NodeIdentity:
    """Immutable identity for a Genesis node."""

    node_id: str
    public_key: bytes
    private_key: bytes

    # -- persistence ---------------------------------------------------------

    def save(self, data_dir: str | Path, password: str | None = None) -> Path:
        """Persist the identity to *data_dir*/:const:`_IDENTITY_FILE`.

        If *password* is provided, the private key is encrypted with
        AES-256-GCM via PBKDF2.  Returns the path written.
        """
        data_dir = Path(data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        filepath = data_dir / _IDENTITY_FILE

        if password:
            flag = _FLAG_ENCRYPTED
            priv_payload = encrypt_private_key(self.private_key, password)
        else:
            flag = _FLAG_PLAIN
            priv_payload = self.private_key

        blob = bytes([flag]) + self.public_key + priv_payload
        filepath.write_bytes(blob)
        # Restrict permissions to owner-only.
        os.chmod(filepath, 0o600)
        return filepath

    @classmethod
    def load(cls, data_dir: str | Path, password: str | None = None) -> NodeIdentity:
        """Load a previously saved identity from *data_dir*.

        Raises ``FileNotFoundError`` if the identity file is missing.
        Raises ``ValueError`` on decryption / format errors.
        """
        filepath = Path(data_dir) / _IDENTITY_FILE
        blob = filepath.read_bytes()

        if len(blob) < 34:
            raise ValueError("Identity file is corrupt (too short)")

        flag = blob[0]
        public_key = blob[1:33]

        if flag == 0x00:
            private_key = blob[33:65]
            if len(private_key) != 32:
                raise ValueError("Identity file is corrupt (bad private key length)")
        elif flag == 0x01:
            encrypted_payload = blob[33:]
            if password is None:
                raise ValueError(
                    "Identity file is encrypted but no password was supplied"
                )
            private_key = decrypt_private_key(encrypted_payload, password)
        else:
            raise ValueError(f"Unknown identity file flag: {flag:#04x}")

        node_id = node_id_from_public_key(public_key)
        return cls(node_id=node_id, public_key=public_key, private_key=private_key)

    # -- factory -------------------------------------------------------------

    @classmethod
    def generate(cls) -> NodeIdentity:
        """Generate a brand-new identity with a fresh Ed25519 key pair."""
        priv, pub = generate_keypair()
        node_id = node_id_from_public_key(pub)
        return cls(node_id=node_id, public_key=pub, private_key=priv)

    @classmethod
    def generate_or_load(
        cls,
        data_dir: str | Path,
        password: str | None = None,
    ) -> NodeIdentity:
        """Load an existing identity or generate (and save) a new one.

        This is the recommended entry point for node startup.
        """
        filepath = Path(data_dir) / _IDENTITY_FILE
        if filepath.exists():
            return cls.load(data_dir, password=password)

        identity = cls.generate()
        identity.save(data_dir, password=password)
        return identity
