"""
Slancio Crypto Algo Treding Engine — Core Security (Encryption)
===================================================
Handles AES-256-GCM encryption/decryption of API Keys using Fernet.
"""

import base64
import os
from loguru import logger
from cryptography.fernet import Fernet
from core.config import get_settings


class EncryptionManager:
    def __init__(self):
        settings = get_settings()
        key = settings.encryption_key
        
        # If no key is set (e.g. in development), generate a temporary one
        if not key:
            logger.warning("No ENCRYPTION_KEY found in environment! Generating a temporary key for this session.")
            key = Fernet.generate_key().decode()
            
        try:
            self.fernet = Fernet(key.encode())
        except ValueError:
            # If the key is invalid format, log it and generate temporary
            logger.error("Invalid ENCRYPTION_KEY format! Must be 32 url-safe base64-encoded bytes. Using temporary key.")
            self.fernet = Fernet(Fernet.generate_key())

    def encrypt(self, plain_text: str) -> str:
        """Encrypts a string and returns a base64 encoded string."""
        if not plain_text:
            return ""
        return self.fernet.encrypt(plain_text.encode()).decode()

    def decrypt(self, encrypted_text: str) -> str:
        """Decrypts a base64 encoded string back to plain text."""
        if not encrypted_text:
            return ""
        try:
            return self.fernet.decrypt(encrypted_text.encode()).decode()
        except Exception as e:
            logger.error(f"Failed to decrypt data. Key mismatch or corrupted data: {e}")
            return ""


# Singleton instance for easy import
security = EncryptionManager()
