import hashlib
from typing import List, Tuple


def exact_duplicate_asset_ids(contents: List[Tuple[int, bytes]]) -> Tuple[List[int], int]:
    """Return duplicate IDs while retaining the oldest exact byte match."""
    seen: dict[str, list[tuple[int, bytes]]] = {}
    duplicate_ids: List[int] = []
    duplicate_digests: set[str] = set()
    for asset_id, content in sorted(contents, key=lambda item: item[0]):
        digest = hashlib.sha256(content).hexdigest()
        matches = seen.setdefault(digest, [])
        if any(previous == content for _, previous in matches):
            duplicate_ids.append(asset_id)
            duplicate_digests.add(digest)
        else:
            matches.append((asset_id, content))
    return duplicate_ids, len(duplicate_digests)
