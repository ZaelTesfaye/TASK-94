"""AES-256-GCM encryption at rest - plan section 7 security controls."""

import base64
import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

from src.logging import logger


def compute_fingerprint_lookup_hash(fingerprint: str) -> str:
    """Deterministic HMAC-SHA256 keyed hash for device fingerprint DB lookup.

    Uses the ENCRYPTION_MASTER_KEY with a fixed context so the same fingerprint
    always produces the same hash. This is safe for equality lookups unlike
    AES-GCM which uses a random IV.
    """
    from src.config import config
    secret = config.ENCRYPTION_MASTER_KEY.encode("utf-8")
    return hmac.new(secret, fingerprint.encode("utf-8"), hashlib.sha256).hexdigest()


def derive_key(master_key: str, context: str) -> bytes:
    """Derive a 256-bit encryption key from a master key using HKDF-SHA256.

    Args:
        master_key: The master key string.
        context: Context string for domain separation (e.g., "field", "pii").

    Returns:
        32-byte derived key suitable for AES-256.
    """
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=context.encode("utf-8"),
    )
    return hkdf.derive(master_key.encode("utf-8"))


def encrypt_field(plaintext: str, master_key: str, context: str = "field") -> str:
    """Encrypt a string field using AES-256-GCM.

    Args:
        plaintext: The string to encrypt.
        master_key: The master encryption key.
        context: HKDF context for key derivation.

    Returns:
        Base64-encoded string containing IV (12 bytes) + ciphertext + tag (16 bytes).
    """
    key = derive_key(master_key, context)
    aesgcm = AESGCM(key)
    iv = os.urandom(12)
    ciphertext = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)
    # ciphertext from AESGCM.encrypt already includes the 16-byte tag appended
    encoded = base64.b64encode(iv + ciphertext).decode("utf-8")
    logger.debug("security", "encryption", "Field encrypted successfully")
    return encoded


def decrypt_field(encrypted: str, master_key: str, context: str = "field") -> str:
    """Decrypt an AES-256-GCM encrypted field.

    Args:
        encrypted: Base64-encoded string (IV + ciphertext + tag).
        master_key: The master encryption key.
        context: HKDF context for key derivation (must match encryption).

    Returns:
        The decrypted plaintext string.

    Raises:
        Exception: If decryption fails (wrong key, tampered data, etc.).
    """
    key = derive_key(master_key, context)
    aesgcm = AESGCM(key)
    raw = base64.b64decode(encrypted)
    iv = raw[:12]
    ciphertext = raw[12:]
    plaintext = aesgcm.decrypt(iv, ciphertext, None)
    logger.debug("security", "encryption", "Field decrypted successfully")
    return plaintext.decode("utf-8")
