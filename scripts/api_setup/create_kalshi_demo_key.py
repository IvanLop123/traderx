#!/usr/bin/env python3
"""Create a local Ed25519 pair for manual registration in Kalshi DEMO only."""
import os
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

root = Path(__file__).resolve().parents[2]
folder = root / 'secrets'
folder.mkdir(mode=0o700, exist_ok=True)
private = folder / 'kalshi_private.pem'
public = folder / 'kalshi_public.pem'
if private.exists() or public.exists():
    raise SystemExit('Existing key material preserved. No files changed.')
key = Ed25519PrivateKey.generate()
for path, data in [
    (private, key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())),
    (public, key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
]:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
print('Local demo key pair created in secrets/. No key contents displayed or transmitted.')
print('Registration is still required: submit only kalshi_public.pem to the DEMO account and save its ID in .env.')
