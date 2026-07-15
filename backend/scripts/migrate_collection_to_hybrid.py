"""
scripts/migrate_collection_to_hybrid.py
=========================================
CLI utility to migrate existing dense-only Qdrant collections to the new
hybrid schema (dense + sparse BM25 vectors) required for Task 2.

DESTRUCTIVE: This script deletes and recreates each collection.
All existing points are re-indexed using their stored `page_content` payloads.

Usage:
    # Migrate a specific collection
    python -m scripts.migrate_collection_to_hybrid --collection my_project

    # Migrate ALL collections
    python -m scripts.migrate_collection_to_hybrid --all

    # Dry-run (show what would happen, no changes)
    python -m scripts.migrate_collection_to_hybrid --all --dry-run
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure backend root is on path when run as __main__
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.services.vector_store_service import VectorStoreService, _encode_sparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("migrate_hybrid")


def _migrate_collection(
    svc: VectorStoreService,
    collection_name: str,
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """
    Scroll all points from an existing collection, delete it, recreate with
    hybrid schema, then re-upsert all points with dense + sparse vectors.
    """
    if not svc._collection_exists(collection_name):
        logger.error("Collection '%s' does not exist. Skipping.", collection_name)
        return

    if svc._is_hybrid_collection(collection_name) and not force:
        logger.info(
            "Collection '%s' is already hybrid. Skipping (use --force to re-index).",
            collection_name,
        )
        return

    # Scroll all existing points
    logger.info("Scrolling all points from '%s'...", collection_name)
    all_points = []
    offset = None
    while True:
        result = svc.client.scroll(
            collection_name=collection_name,
            limit=200,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        points, next_offset = result
        all_points.extend(points)
        if next_offset is None:
            break
        offset = next_offset

    logger.info("Found %d points in '%s'.", len(all_points), collection_name)

    if dry_run:
        logger.info(
            "[DRY-RUN] Would delete '%s' and recreate with hybrid schema (%d points).",
            collection_name, len(all_points),
        )
        return

    # Delete old collection
    logger.info("Deleting existing collection '%s'...", collection_name)
    svc.client.delete_collection(collection_name)

    # Recreate with hybrid schema
    svc._ensure_collection(collection_name)
    logger.info("Created hybrid collection '%s'.", collection_name)

    if not all_points:
        logger.info("No points to re-index for '%s'. Done.", collection_name)
        return

    # Re-compute sparse vectors from stored page_content
    texts = [p.payload.get("page_content", "") for p in all_points]
    logger.info("Encoding %d sparse vectors (BM25)...", len(texts))
    sparse_vecs = _encode_sparse(texts)

    from qdrant_client.models import PointStruct, SparseVector
    import uuid

    new_points = []
    for point, sparse in zip(all_points, sparse_vecs):
        payload = point.payload or {}
        # Re-use the stored dense vector if available
        old_vector = point.vector
        if isinstance(old_vector, list):
            dense_vector = old_vector
        elif isinstance(old_vector, dict):
            # Already named — grab "dense" or first entry
            dense_vector = old_vector.get("dense", list(old_vector.values())[0])
        else:
            logger.warning("Point %s has no usable dense vector; skipping.", point.id)
            continue

        vector: dict = {"dense": dense_vector}
        if sparse is not None:
            vector["sparse"] = sparse

        new_points.append(
            PointStruct(
                id=str(point.id),
                vector=vector,
                payload=payload,
            )
        )

    # Upsert in batches
    batch_size = 200
    for i in range(0, len(new_points), batch_size):
        svc.client.upsert(
            collection_name=collection_name,
            points=new_points[i : i + batch_size],
        )
        logger.info(
            "Upserted batch %d/%d for '%s'.",
            min(i + batch_size, len(new_points)), len(new_points), collection_name,
        )

    logger.info(
        "✅ Migration complete for '%s': %d points re-indexed.",
        collection_name, len(new_points),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate Qdrant collections from dense-only to hybrid (dense + sparse) schema."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--collection", metavar="NAME", help="Migrate a single collection.")
    group.add_argument("--all", action="store_true", help="Migrate all existing collections.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without making any changes.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force migration and re-indexing even if the collection is already hybrid.",
    )
    args = parser.parse_args()

    settings = get_settings()
    svc = VectorStoreService(settings)

    if args.all:
        try:
            collections = svc.client.get_collections().collections
            names = [c.name for c in collections]
        except Exception as exc:
            logger.error("Cannot list Qdrant collections: %s", exc)
            sys.exit(1)

        if not names:
            logger.info("No collections found. Nothing to migrate.")
            return

        logger.info("Found %d collection(s): %s", len(names), names)
        for name in names:
            _migrate_collection(svc, name, dry_run=args.dry_run, force=args.force)
    else:
        _migrate_collection(svc, args.collection, dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    main()
