"""
See COPYRIGHT.md for copyright information.

TypeKey canonicalization + dedup cache.

Equivalence identity is the ``FacetSet`` (base + canonically-sorted facets, with
enumeration/pattern order preserved); two testGroups with the same identity share a
single ``gen-<key>.xsd``. The ``TypeKey`` doubles as the filename slug, so it must
be deterministic across process runs and filesystem-safe:

- built-in type with no facets -> the bare base localName (e.g. ``string``);
- otherwise a human-readable slug (``decimal__minExclusive_-999``) plus a short,
  content-derived hash whenever the slug would be lossy (sanitized/truncated) or
  carries enumerations/patterns whose values don't slug cleanly.

The hash is derived from a JSON canonicalization of the ``FacetSet`` (stable, and
unambiguous thanks to JSON escaping), never from Python's randomized ``hash()``.
"""

from __future__ import annotations

import hashlib
import json
import re

from xbrl_xsdtests.model import (
    ExtractedType,
    FacetSet,
    TypeKey,
)

_MAX_SLUG = 80
_HASH_LEN = 8
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


class TaxonomyDedup:
    """Caches ``FacetSet`` identities to ``TypeKey``s, collapsing equivalents."""

    def __init__(self) -> None:
        self._by_facets: dict[FacetSet, TypeKey] = {}
        self._used: dict[str, FacetSet] = {}

    def key_for(self, t: ExtractedType) -> TypeKey:
        """Return the canonical ``TypeKey`` for a type (pure; ignores the cache)."""
        return self._key_for_facets(t.facet_set)

    def get_or_register(self, t: ExtractedType) -> tuple[TypeKey, bool]:
        """Return ``(key, is_new)``; ``is_new`` is False for an already-seen type."""
        facet_set = t.facet_set
        existing = self._by_facets.get(facet_set)
        if existing is not None:
            return existing, False
        key = self._key_for_facets(facet_set)
        collided_with = self._used.get(key.value)
        if collided_with is not None and collided_with != facet_set:
            # Defensive: distinct identities sharing a slug get a longer hash.
            key = TypeKey(f"{key.value}-{self._hash(facet_set, length=16)}")
        self._by_facets[facet_set] = key
        self._used[key.value] = facet_set
        return key, True

    def _key_for_facets(self, facet_set: FacetSet) -> TypeKey:
        if not facet_set.facets and not facet_set.enumerations and not facet_set.patterns:
            sanitized, _lossy = self._sanitize(facet_set.base_xsd)
            return TypeKey(sanitized)
        readable = self._readable(facet_set)
        sanitized, lossy = self._sanitize(readable)
        needs_hash = (
            lossy
            or len(sanitized) > _MAX_SLUG
            or bool(facet_set.enumerations)
            or bool(facet_set.patterns)
        )
        if not needs_hash:
            return TypeKey(sanitized)
        prefix = sanitized[:_MAX_SLUG].rstrip("._-")
        return TypeKey(f"{prefix}-{self._hash(facet_set)}")

    @staticmethod
    def _readable(facet_set: FacetSet) -> str:
        parts = [facet_set.base_xsd]
        for name, value in facet_set.facets:
            parts.append(f"{name}_{value}")
        return "__".join(parts)

    @staticmethod
    def _sanitize(text: str) -> tuple[str, bool]:
        clean = _UNSAFE.sub("_", text)
        return clean, clean != text

    @staticmethod
    def _canonical(facet_set: FacetSet) -> str:
        return json.dumps(
            {
                "base": facet_set.base_xsd,
                "facets": [list(f) for f in facet_set.facets],
                "enumerations": list(facet_set.enumerations),
                "patterns": list(facet_set.patterns),
            },
            ensure_ascii=True,
            separators=(",", ":"),
        )

    @classmethod
    def _hash(cls, facet_set: FacetSet, length: int = _HASH_LEN) -> str:
        return hashlib.sha1(cls._canonical(facet_set).encode("utf-8")).hexdigest()[:length]
