"""
Finance Wise TBM — License Key Generator
==========================================
Run this script on YOUR machine to generate activation keys for clients.
Never share this file or the LICENSOR_SECRET with anyone.

Usage:
    python generate_license.py

It will prompt you for the client's Machine ID and print their key.

You can also use it in batch mode:
    python generate_license.py <machine_id>
"""

import sys
import os

# Make sure licensing.py is importable from the chama_system folder
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'chama_system'))

from licensing import generate_key, get_machine_id


def main():
    print()
    print("=" * 55)
    print("  Finance Wise TBM — License Key Generator")
    print("=" * 55)

    if len(sys.argv) > 1:
        machine_id = sys.argv[1].strip().upper()
    else:
        print()
        print("Paste the Machine ID from the client's activation screen:")
        print()
        machine_id = input("  Machine ID: ").strip().upper()

    if not machine_id:
        print("\nNo machine ID provided. Exiting.")
        sys.exit(1)

    key = generate_key(machine_id)

    print()
    print("-" * 55)
    print(f"  Machine ID  : {machine_id}")
    print(f"  License Key : {key}")
    print("-" * 55)
    print()
    print("Send the License Key to the client.")
    print("They enter it in the activation screen on first launch.")
    print()

    # Also print your own machine ID for reference
    try:
        my_id = get_machine_id()
        if my_id != machine_id:
            print(f"(Your machine ID is: {my_id})")
            print()
    except Exception:
        pass


if __name__ == "__main__":
    main()
