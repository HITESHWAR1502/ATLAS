"""
ATCG DB Init Script — Initialize the Neon database schema.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from atcg.config import ATCGConfig
from atcg.db.connection import NeonConnection
from atcg.db.migrations import initialize_schema, get_schema_status


async def main():
    dry_run = "--dry-run" in sys.argv

    print("ATCG v3.0 — Database Schema Initialization")
    print("=" * 50)

    try:
        config = ATCGConfig.from_env()
    except ValueError as e:
        print(f"ERROR: {e}")
        print("Copy .env.example to .env and configure your credentials.")
        sys.exit(1)

    db = NeonConnection(config)
    await db.initialize()

    try:
        health = await db.health_check()
        print(f"Connection: {'✓ OK' if health else '✗ FAILED'}")

        if not health:
            print("Cannot connect to Neon. Check your NEON_DATABASE_URL.")
            sys.exit(1)

        if dry_run:
            print("\n[DRY RUN] Would create the following tables:\n")

        tables = await initialize_schema(db, dry_run=dry_run)

        if not dry_run:
            print(f"\n✓ {len(tables)} tables created/verified")

            print("\nSchema Status:")
            status = await get_schema_status(db)
            for name, info in status.items():
                exists = "✓" if info.get("exists") else "✗"
                rows = info.get("row_count", 0)
                print(f"  {exists} {name}: {rows} rows")

    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
