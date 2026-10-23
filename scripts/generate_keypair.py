#!/usr/bin/env python3
"""
Developer Key Generation Tool for Finance Wise TBM Releases.
============================================================
Generates a cryptographically secure Ed25519 keypair for signing releases.
"""

import os
import sys

# Add parent directory to path to import updater modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "chama_system")))

from updater.crypto import sign_data
from updater.ed25519_pure import generate_keypair


def main():
    print("=" * 64)
    print("Finance Wise TBM — Release Signing Keypair Generator")
    print("=" * 64)
    print()

    sk_hex, pk_hex = generate_keypair()

    print("Generated Ed25519 Keypair:")
    print("-" * 64)
    print(f"PRIVATE KEY (SEED) : {sk_hex}")
    print(f"PUBLIC KEY         : {pk_hex}")
    print("-" * 64)
    print()
    print("CRITICAL SECURITY INSTRUCTIONS:")
    print("1. KEEP THE PRIVATE KEY CONFIDENTIAL. Never commit it to git or bundle it in the desktop app.")
    print("2. In GitHub, add this as a secret:")
    print("   Repository Settings -> Secrets and variables -> Actions -> New repository secret")
    print("   Name : RELEASE_SIGNING_PRIVATE_KEY")
    print(f"   Value: {sk_hex}")
    print()
    print("3. Set the PUBLIC KEY in your application config or updater/crypto.py:")
    print(f"   DEFAULT_UPDATER_PUBLIC_KEY = '{pk_hex}'")
    print("   Or set UPDATER_PUBLIC_KEY in .env or GitHub Actions.")
    print("=" * 64)


if __name__ == "__main__":
    main()
