"""Shannon entropy heuristic for the scanner engine. See Section 8.3.

Applied naively this produces enough noise to make the feature useless — hashes,
UUIDs, base64 images, and minified JS all look random too. Three guards keep it
useful:
  - Only score strings assigned to a credential-shaped variable name (key, token,
    secret, password, auth, credential).
  - Minimum length 32 chars, threshold ~4.5 bits/char for a base64-like alphabet.
  - Exclude known-benign shapes: UUIDs, git SHAs, standard hash lengths, data URIs.

An entropy finding is always classified NEEDS_REVIEW, never CRITICAL — it's a hint,
not a determination.
"""

from __future__ import annotations

import math
import re

_CREDENTIAL_NAME_HINT = re.compile(r"(key|token|secret|password|auth|credential)", re.IGNORECASE)
_MIN_LENGTH = 32
_ENTROPY_THRESHOLD_BITS = 4.5

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$|^[0-9a-f]{7,10}$", re.IGNORECASE)
_HEX_HASH_LENGTHS = {32, 40, 56, 64, 96, 128}  # md5, sha1, sha224, sha256, sha384, sha512
_DATA_URI_PREFIX = "data:"


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts: dict[str, int] = {}
    for ch in value:
        counts[ch] = counts.get(ch, 0) + 1
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def is_known_benign_shape(value: str) -> bool:
    if _UUID_RE.match(value):
        return True
    if _GIT_SHA_RE.match(value) and all(c in "0123456789abcdefABCDEF" for c in value):
        return True
    if len(value) in _HEX_HASH_LENGTHS and all(c in "0123456789abcdefABCDEF" for c in value):
        return True
    return bool(value.startswith(_DATA_URI_PREFIX))


def looks_like_credential(variable_name: str, value: str) -> bool:
    if not _CREDENTIAL_NAME_HINT.search(variable_name):
        return False
    if len(value) < _MIN_LENGTH:
        return False
    if is_known_benign_shape(value):
        return False
    return shannon_entropy(value) >= _ENTROPY_THRESHOLD_BITS
