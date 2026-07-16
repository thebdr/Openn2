"""The universal content-hash key (`uid`) for every PL4 entity and finding.

A `uid` is a short, stable SHA-1 hash of an entity's IDENTIFYING content - the fields that define
*what it is* - deliberately EXCLUDING volatile context (a workbook filename, a run sequence number, a
log level). That exclusion is the whole point: the same signal (or the same validation finding) keeps
its `uid` across a document revision, so a treatment attached to it - and every created entity that
references it - survives. This generalizes Pipeline3's finding-uid (`sha1(phase|type|location|detail)`).

Usage rule: pass ONLY the stable identifying fields. Never feed in a workbook name, a sequence number,
or anything that changes when the documents are merely re-saved or rearranged.
"""
from __future__ import annotations

import hashlib

UID_HEX_LENGTH = 10   # hex chars; matches PL3 (sha1[:10]) - ample for these data volumes


def uid(*parts) -> str:
    """A stable `UID_HEX_LENGTH`-char hex hash of `parts`, joined by '|'. Each part is stringified
    (`None` -> ''). The same parts always yield the same uid; changing or adding any part changes it."""
    basis = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:UID_HEX_LENGTH]
