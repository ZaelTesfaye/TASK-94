"""Unit tests for AES-256-GCM encryption module."""
import pytest

from src.security.encryption import encrypt_field, decrypt_field


MASTER_KEY = "test-master-key-for-unit-tests"


def test_encrypt_decrypt_roundtrip():
    """Encrypting then decrypting should return the original plaintext."""
    plaintext = "hello world"
    encrypted = encrypt_field(plaintext, MASTER_KEY)
    decrypted = decrypt_field(encrypted, MASTER_KEY)
    assert decrypted == plaintext


def test_encrypt_produces_different_ciphertext():
    """Encrypting the same text twice should produce different output (random IV)."""
    plaintext = "same plaintext"
    c1 = encrypt_field(plaintext, MASTER_KEY)
    c2 = encrypt_field(plaintext, MASTER_KEY)
    assert c1 != c2


def test_decrypt_wrong_key_fails():
    """Decrypting with a different key should raise an exception."""
    encrypted = encrypt_field("secret data", MASTER_KEY)
    with pytest.raises(Exception):
        decrypt_field(encrypted, "wrong-master-key-entirely")


def test_encrypt_empty_string():
    """Encrypting and decrypting an empty string should roundtrip correctly."""
    encrypted = encrypt_field("", MASTER_KEY)
    decrypted = decrypt_field(encrypted, MASTER_KEY)
    assert decrypted == ""


def test_different_contexts_produce_different_results():
    """Same key but different HKDF context strings should produce different ciphertext."""
    plaintext = "context test"
    c1 = encrypt_field(plaintext, MASTER_KEY, context="context-a")
    c2 = encrypt_field(plaintext, MASTER_KEY, context="context-b")
    # Even though IV randomness already makes them differ, the derived keys
    # are also different so decrypting with the wrong context must fail.
    assert c1 != c2
    # Verify cross-context decryption fails
    with pytest.raises(Exception):
        decrypt_field(c1, MASTER_KEY, context="context-b")
