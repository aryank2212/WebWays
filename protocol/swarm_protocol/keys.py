"""ed25519 publisher identity. A public key *is* the publisher's identity."""
from __future__ import annotations

import base64
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .errors import ProtocolError


def b64u_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64u_decode(text: str) -> bytes:
    if not isinstance(text, str) or not text.isascii():
        raise ProtocolError("bad base64url")
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except Exception as exc:
        raise ProtocolError("bad base64url") from exc


@dataclass(frozen=True)
class Identity:
    private: Ed25519PrivateKey

    @classmethod
    def generate(cls) -> "Identity":
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def load(cls, path: str | Path) -> "Identity":
        seed = b64u_decode(Path(path).read_text().strip())
        if len(seed) != 32:
            raise ProtocolError("key file must hold a 32-byte seed")
        return cls(Ed25519PrivateKey.from_private_bytes(seed))

    @classmethod
    def load_or_create(cls, path: str | Path) -> "Identity":
        path = Path(path)
        if path.exists():
            return cls.load(path)
        ident = cls.generate()
        ident.save(path)
        return ident

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        seed = self.private.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "w") as fh:
            fh.write(b64u_encode(seed) + "\n")

    @property
    def public_key(self) -> str:
        raw = self.private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        return b64u_encode(raw)

    def sign(self, message: bytes) -> str:
        return b64u_encode(self.private.sign(message))


def verify(public_key: str, signature: str, message: bytes) -> None:
    """Raise ProtocolError unless `signature` is a valid ed25519 signature."""
    pub = b64u_decode(public_key)
    sig = b64u_decode(signature)
    if len(pub) != 32 or len(sig) != 64:
        raise ProtocolError("bad key or signature length")
    try:
        Ed25519PublicKey.from_public_bytes(pub).verify(sig, message)
    except InvalidSignature as exc:
        raise ProtocolError("signature does not verify") from exc
