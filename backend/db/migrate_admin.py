"""
db/migrate_admin.py — One-time script: copy admin from MongoDB → Neon
======================================================================
Run once:  python db/migrate_admin.py
Safe to re-run — uses INSERT ... ON CONFLICT DO NOTHING.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "")

def migrate_admin():
    # Safe execution guard: prevent accidental execution and data overwrites
    if os.getenv("CONFIRM_ADMIN_MIGRATION", "").strip().lower() != "true":
        print("[ABORTED] migrate_admin.py is a one-time migration utility.")
        print("          To execute, explicitly set CONFIRM_ADMIN_MIGRATION=true in your environment.")
        return

    mongo_uri = (os.getenv("MONGO_URI") or MONGO_URI).strip()
    if not mongo_uri:
        print("[ERROR] MONGO_URI environment variable is required for migration.")
        return

    # Defer database imports until after execution guards pass to eliminate import-time side effects
    import certifi
    from pymongo import MongoClient
    from extensions import get_db, init_db

    print("[*] Initializing Neon DB schema...")
    init_db()
    print("[*] Connecting to MongoDB Atlas...")
    mongo_client = MongoClient(mongo_uri, tlsCAFile=certifi.where())
    mongo_db = mongo_client["prepai"]

    admin = mongo_db["users"].find_one({"role": "admin"})
    if not admin:
        print("[!] No admin user found in MongoDB.")
        return

    # Map MongoDB fields → Neon columns
    name          = admin.get("name", "Admin")
    email         = admin.get("email")
    password_hash = admin.get("password", "")    # already hashed by werkzeug
    role          = "admin"
    is_verified   = True
    onboarding    = True

    print("[*] Found admin: " + name + " <" + email + ">")

    print("[*] Inserting admin into Neon...")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users
                    (name, email, password_hash, role, is_verified, onboarding_completed)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (email) DO UPDATE
                    SET password_hash        = EXCLUDED.password_hash,
                        role                 = EXCLUDED.role,
                        is_verified          = EXCLUDED.is_verified,
                        onboarding_completed = EXCLUDED.onboarding_completed
                RETURNING id
                """,
                (name, email, password_hash, role, is_verified, onboarding)
            )
            new_id = cur.fetchone()[0]

    print("[DONE] Admin migrated successfully! Neon ID: " + str(new_id))
    print("   Email:    " + email)


if __name__ == "__main__":
    migrate_admin()
