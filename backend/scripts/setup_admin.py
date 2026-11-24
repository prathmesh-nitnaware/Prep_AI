"""
backend/scripts/setup_admin.py — Legacy Administrator Setup Script (DISARMED)
=============================================================================
HISTORICAL CONTEXT:
This script was originally used to provision an initial administrator in MongoDB.
Following the migration to Neon PostgreSQL and strict credential sanitization,
direct creation of administrative accounts via hardcoded credentials in this
script has been permanently disarmed.

Administrator accounts must be provisioned through secure, authenticated
application workflows or managed PostgreSQL administration.
"""
import sys


def setup_admin():
    """
    Disarmed administrative setup routine.
    Refuses execution to prevent hardcoded credential usage or unmanaged database writes.
    """
    print("[ERROR] backend/scripts/setup_admin.py is obsolete and has been disarmed.")
    print("        Direct administrator creation via this legacy script is disabled.")
    print("        No database connections or modifications were performed.")
    sys.exit(1)


if __name__ == "__main__":
    setup_admin()
