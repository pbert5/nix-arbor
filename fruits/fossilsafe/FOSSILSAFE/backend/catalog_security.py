"""
Catalog security and signing utilities.
Handles Ed25519 keypair generation, catalog signing, and verification.
"""
import os
import json
import hashlib
import base64
from pathlib import Path
from typing import Dict, Optional, Tuple
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature
import logging

from backend.config_store import get_data_dir

logger = logging.getLogger(__name__)

def get_keys_dir() -> Path:
    override = os.environ.get("FOSSILSAFE_KEYS_DIR")
    if override:
        return Path(os.path.abspath(os.path.expanduser(override)))
    return Path(get_data_dir()) / "keys"


def get_private_key_path() -> Path:
    return get_keys_dir() / "appliance.key"


def get_public_key_path() -> Path:
    return get_keys_dir() / "appliance.pub"


def ensure_keypair(passphrase: Optional[str] = None) -> Tuple[str, str]:
    """
    Ensure Ed25519 keypair exists. Generate if missing.
    Returns (public_key_pem, key_id)
    """
    keys_dir = get_keys_dir()
    private_key_path = get_private_key_path()
    public_key_path = get_public_key_path()

    keys_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    
    if private_key_path.exists() and public_key_path.exists():
        # Load existing keys
        with open(public_key_path, 'rb') as f:
            public_pem = f.read().decode('utf-8')
        key_id = _generate_key_id(public_pem)
        return public_pem, key_id
    
    # Generate new keypair
    logger.info("Generating new Ed25519 keypair for catalog signing")
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    # Serialize private key (encrypted if passphrase provided)
    if passphrase:
        encryption = serialization.BestAvailableEncryption(passphrase.encode())
    else:
        encryption = serialization.NoEncryption()
    
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=encryption
    )
    
    # Serialize public key
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    # Save keys
    with open(private_key_path, 'wb') as f:
        f.write(private_pem)
    os.chmod(private_key_path, 0o600)
    
    with open(public_key_path, 'wb') as f:
        f.write(public_pem)
    os.chmod(public_key_path, 0o644)
    
    public_pem_str = public_pem.decode('utf-8')
    key_id = _generate_key_id(public_pem_str)
    
    logger.info(f"Generated keypair with ID: {key_id}")
    return public_pem_str, key_id


def _generate_key_id(public_pem: str) -> str:
    """Generate a short key ID from public key."""
    key_hash = hashlib.sha256(public_pem.encode()).hexdigest()
    return f"appliance_key_{key_hash[:12]}"


def sign_catalog(catalog_data: Dict, passphrase: Optional[str] = None) -> Dict:
    """
    Sign a catalog dictionary and return it with security metadata.
    
    Args:
        catalog_data: Catalog dict (without 'security' field)
        passphrase: Optional passphrase for private key
        
    Returns:
        Catalog dict with 'security' field added
    """
    # Ensure keypair exists
    public_pem, key_id = ensure_keypair(passphrase)
    
    # Calculate catalog hash (canonical JSON, sorted keys)
    catalog_json = json.dumps(catalog_data, sort_keys=True, separators=(',', ':'))
    catalog_hash = hashlib.sha256(catalog_json.encode()).hexdigest()
    
    # Load private key
    try:
        with open(get_private_key_path(), 'rb') as f:
            private_pem = f.read()
        
        if passphrase:
            private_key = serialization.load_pem_private_key(
                private_pem,
                password=passphrase.encode()
            )
        else:
            private_key = serialization.load_pem_private_key(
                private_pem,
                password=None
            )
    except Exception as e:
        logger.error(f"Failed to load private key: {e}")
        raise
    
    # Sign the hash
    signature = private_key.sign(catalog_hash.encode())
    signature_b64 = base64.b64encode(signature).decode('utf-8')
    
    # Add security metadata
    catalog_data['security'] = {
        'catalog_hash': f'sha256:{catalog_hash}',
        'signature': signature_b64,
        'signing_key_id': key_id,
        'public_key': public_pem,
        'chain_of_trust': catalog_data.get('chain_of_trust', {})
    }
    
    return catalog_data


def verify_catalog(catalog_data: Dict) -> Tuple[bool, str]:
    """
    Verify catalog signature and integrity.
    
    Returns:
        (is_valid, message)
    """
    if 'security' not in catalog_data:
        return False, "No security metadata found (legacy tape)"
    
    security = catalog_data['security']
    
    # Extract security fields
    stored_hash = security.get('catalog_hash', '')
    signature_b64 = security.get('signature', '')
    public_pem = security.get('public_key', '')
    
    if not all([stored_hash, signature_b64, public_pem]):
        return False, "Incomplete security metadata"
    
    # Remove security field for hash calculation
    catalog_copy = dict(catalog_data)
    del catalog_copy['security']
    
    # Recalculate hash
    catalog_json = json.dumps(catalog_copy, sort_keys=True, separators=(',', ':'))
    calculated_hash = hashlib.sha256(catalog_json.encode()).hexdigest()
    
    # Verify hash matches
    if stored_hash != f'sha256:{calculated_hash}':
        return False, "Catalog hash mismatch (tampered)"
    
    # Verify signature
    try:
        public_key = serialization.load_pem_public_key(public_pem.encode())
        signature = base64.b64decode(signature_b64)
        public_key.verify(signature, calculated_hash.encode())
        return True, "Catalog verified successfully"
    except InvalidSignature:
        return False, "Invalid signature (forged)"
    except Exception as e:
        return False, f"Verification error: {e}"


def get_trust_level(catalog_data: Dict) -> str:
    """
    Determine trust level of catalog.
    Returns: 'trusted', 'partial', or 'untrusted'
    """
    is_valid, message = verify_catalog(catalog_data)
    
    if is_valid:
        return 'trusted'
    elif 'No security metadata' in message:
        return 'partial'  # Legacy tape
    else:
        return 'untrusted'  # Tampered or forged
