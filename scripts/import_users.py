#!/usr/bin/env python
"""Bulk‑import users into MongoDB from a CSV file **(updated May 2025)**.

Usage (single line):
    python scripts/import_users.py --file users.csv --mongo "mongodb://localhost:27017/intranet" --default-password password

CSV expected columns (header row – order irrelevant):
    nome,email,ruolo,filiale,tipologia assunzione,bu,team,nascita,sesso,cittadinanza,password?

The header names are case‑ and space‑insensitive; synonyms in Italian/English are accepted:
    nome|name  → name
    filiale|branch → branch
    tipologia assunzione|hire_type|employment_type → hire_type
    nascita|birth_date|data di nascita → birth_date

Notes
-----
* If *password* is empty or missing the password passed via --default-password
  (default: "password") is used.
* Dates are accepted as dd/mm/yyyy or yyyy-mm-dd and stored as ISO yyyy-mm-dd.
* The script performs an **upsert** keyed on e‑mail, so it can be run multiple
  times; it will update existing users and create the missing ones.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
from datetime import datetime
from pathlib import Path
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient
from passlib.hash import bcrypt

ISO_FMT = "%Y-%m-%d"  # ISO‑8601 we store in Mongo

# ---------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------


def _to_key(s: str) -> str:
    """Normalise *s*: lowercase, strip spaces, collapse inner spaces."""
    return " ".join(s.lower().split())


def _parse_date(raw: Optional[str]) -> Optional[str]:
    """Parse *raw* date (dd/mm/yyyy or yyyy-mm-dd) → ISO string or None."""
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime(ISO_FMT)
        except ValueError:
            continue
    print(f"[WARN] invalid date '{raw}', left empty")
    return None


# mapping of Italian/alternative header names → canonical key used in DB
CANON_MAP = {
    "nome": "name",
    "name": "name",
    "email": "email",
    "ruolo": "role",
    "role": "role",
    "filiale": "branch",
    "branch": "branch",
    "tipologia assunzione": "employment_type",
    "hire_type": "employment_type",
    "employment_type": "employment_type",
    "bu": "bu",
    "team": "team",
    "nascita": "birth_date",
    "data di nascita": "birth_date",
    "birth_date": "birth_date",
    "sesso": "sex",
    "sex": "sex",
    "cittadinanza": "citizenship",
    "citizenship": "citizenship",
    "password": "password",
}

# default values when a column is missing or empty
DEFAULTS = {
    "role": "staff",
    "branch": "HQE",
}


async def import_users(csv_path: Path, mongo_uri: str, default_pw: str) -> None:
    """Read *csv_path* and upsert users into Mongo at *mongo_uri*."""

    client = AsyncIOMotorClient(mongo_uri)
    db = client.get_default_database()

    created = updated = skipped = 0

    with csv_path.open(newline="", encoding="utf-8-sig") as fp:
        # auto‑detect delimiter (comma or semicolon)
        sample = fp.read(4096)
        fp.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=",;")
        reader = csv.DictReader(fp, dialect=dialect)

        # ------- header normalisation ----------
        original_headers = reader.fieldnames or []
        canon_headers = [_to_key(h) for h in original_headers]
        reader.fieldnames = canon_headers  # mutate in‑place so DictReader uses them

        # ------- rows ----------
        for raw in reader:
            # raw keys are already canonicalised; clone and strip values
            row = {k: (v or "").strip() for k, v in raw.items()}

            # build base document with canonical keys ONLY
            doc: dict[str, Optional[str]] = {}
            for key, value in row.items():
                canonical = CANON_MAP.get(key, key)
                if canonical == "email":
                    value = value.lower()
                if value:
                    doc[canonical] = value

            # ensure mandatory email
            email = doc.get("email")
            if not email:
                print("[WARN] skipped row with empty e-mail")
                skipped += 1
                continue

            # defaults & transforms
            doc.setdefault("role", DEFAULTS["role"])
            doc.setdefault("branch", DEFAULTS["branch"])
            doc["birth_date"] = _parse_date(doc.get("birth_date")) if doc.get("birth_date") else None
            doc["sex"] = doc.get("sex", "").upper() or None
            doc["branch"] = doc["branch"].upper()
            if "employment_type" in doc:
                doc["employment_type"] = doc["employment_type"].lower() or None

            # password hash handling
            password_plain = doc.pop("password", None) or default_pw
            doc["pass_hash"] = bcrypt.hash(password_plain)
            doc["must_change_pw"] = True

            # upsert
            res = await db.users.update_one({"email": email}, {"$set": doc}, upsert=True)
            if res.upserted_id:
                created += 1
            elif res.modified_count:
                updated += 1
            else:
                skipped += 1

    print(f"Created: {created}, Updated: {updated}, Skipped: {skipped}")


# ---------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import users from CSV into MongoDB")
    parser.add_argument("--file", required=True, help="Path to CSV file")
    parser.add_argument("--mongo", default="mongodb://localhost:27017/intranet", help="Mongo URI")
    parser.add_argument("--default-password", default="password", help="Password to assign when missing in CSV")

    args = parser.parse_args()
    csv_path = Path(args.file)

    # If the path is relative and the file does NOT exist in cwd, try next to this script
    if not csv_path.is_absolute() and not csv_path.exists():
        csv_path = Path(__file__).parent / csv_path

    asyncio.run(import_users(csv_path, args.mongo, args.default_password))
