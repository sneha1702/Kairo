#!/usr/bin/env python3
"""
purge.py — Wipe Kairo Elasticsearch indices and/or MongoDB collections on demand.

Usage:
  python scripts/purge.py --all             # purge both ES and MongoDB
  python scripts/purge.py --elastic         # purge ES indices only
  python scripts/purge.py --mongo           # purge MongoDB collections only
  python scripts/purge.py --all --dry-run   # preview without deleting

Credentials are loaded from `brain.config.Config`, which itself reads environment variables and .env values.
"""

import argparse
import os
import sys

# ── .env loading (optional) ────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Ensure repo root is on PYTHONPATH for direct script execution
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# ── Constants ──────────────────────────────────────────────────────────────────

ES_INDICES = [
    "dune_whale_transactions",
    "dune_smart_money",
    "dune_token_flows",
    "dune_bridge_activity",
    "dune_wallet_concentration",
    "dune_volume_spikes",
    "dune_holder_growth",
    "dune_dex_concentration",
    "whale_transactions",
]

MONGO_COLLECTIONS = [
    "narratives",
    "narrative_history",
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _confirm(prompt: str) -> bool:
    try:
        ans = input(f"{prompt} [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return ans == "y"


# ── Purge functions ────────────────────────────────────────────────────────────

def purge_elasticsearch(dry_run: bool) -> None:
    try:
        from elasticsearch import Elasticsearch, NotFoundError
    except ImportError:
        print("ERROR: 'elasticsearch' package not installed. Run: pip install elasticsearch")
        sys.exit(1)

    from brain.config import Config

    es_url      = Config.ES_URL
    es_username = Config.ES_USERNAME
    es_password = Config.ES_PASSWORD
    api_key_id  = Config.ES_API_KEY_ID

    if not es_url:
        print("ERROR: ES_URL is not configured in brain.config.Config.")
        sys.exit(1)

    if api_key_id:
        es = Elasticsearch(es_url, api_key=api_key_id)
    elif es_username and es_password:
        es = Elasticsearch(es_url, basic_auth=(es_username, es_password))
    else:
        es = Elasticsearch(es_url)

    print("\n── Elasticsearch ──────────────────────────────────────")
    for idx in ES_INDICES:
        try:
            exists = es.indices.exists(index=idx)
        except Exception as exc:
            print(f"  [{idx}] SKIP (could not check existence: {exc})")
            continue

        if not exists:
            print(f"  [{idx}] not found — skipping")
            continue

        count_resp = es.count(index=idx)
        doc_count  = count_resp.get("count", "?")
        print(f"  [{idx}] {doc_count} documents", end="")

        if dry_run:
            print("  → DRY RUN, would delete")
        else:
            try:
                es.indices.delete(index=idx)
                print("  → DELETED")
            except Exception as exc:
                print(f"  → ERROR: {exc}")

    print()


def purge_mongodb(dry_run: bool) -> None:
    try:
        from pymongo import MongoClient
    except ImportError:
        print("ERROR: 'pymongo' package not installed. Run: pip install pymongo")
        sys.exit(1)

    from brain.config import Config

    mongo_uri = Config.MONGO_URI
    mongo_db  = Config.MONGO_DB or "kairo"

    if not mongo_uri:
        print("ERROR: MONGO_URI is not configured in brain.config.Config.")
        sys.exit(1)

    client = MongoClient(mongo_uri)
    db     = client[mongo_db]

    print(f"\n── MongoDB  ({mongo_db}) ────────────────────────────────")
    existing = set(db.list_collection_names())

    for col in MONGO_COLLECTIONS:
        if col not in existing:
            print(f"  [{col}] not found — skipping")
            continue

        doc_count = db[col].estimated_document_count()
        print(f"  [{col}] ~{doc_count} documents", end="")

        if dry_run:
            print("  → DRY RUN, would drop")
        else:
            try:
                db[col].drop()
                print("  → DROPPED")
            except Exception as exc:
                print(f"  → ERROR: {exc}")

    print()
    client.close()


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Purge Kairo Elasticsearch indices and/or MongoDB collections."
    )
    parser.add_argument("--elastic",  action="store_true", help="Purge Elasticsearch indices")
    parser.add_argument("--mongo",    action="store_true", help="Purge MongoDB collections")
    parser.add_argument("--all",      action="store_true", help="Purge both ES and MongoDB")
    parser.add_argument("--dry-run",  action="store_true", help="Preview what would be deleted without actually deleting")
    parser.add_argument("--yes",      action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    do_elastic = args.elastic or args.all
    do_mongo   = args.mongo   or args.all

    if not do_elastic and not do_mongo:
        parser.print_help()
        sys.exit(0)

    targets = []
    if do_elastic:
        targets.append(f"Elasticsearch ({len(ES_INDICES)} indices)")
    if do_mongo:
        targets.append(f"MongoDB collections ({', '.join(MONGO_COLLECTIONS)})")

    print(f"\nKairo Purge Script")
    print(f"Targets : {' + '.join(targets)}")
    print(f"Dry-run : {'YES — no data will be deleted' if args.dry_run else 'NO — data will be permanently deleted'}")

    if not args.dry_run and not args.yes:
        if not _confirm("\nProceed?"):
            print("Aborted.")
            sys.exit(0)

    if do_elastic:
        purge_elasticsearch(dry_run=args.dry_run)

    if do_mongo:
        purge_mongodb(dry_run=args.dry_run)

    if args.dry_run:
        print("Dry run complete — nothing was deleted.")
    else:
        print("Purge complete.")


if __name__ == "__main__":
    main()
