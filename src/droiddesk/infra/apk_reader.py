"""ApkReader: facade over androguard and pyaxmlparser. See Section 6.2 and the
Performance note there — pyaxmlparser for the fast identity panel, full androguard
analysis loaded lazily only when a panel needs it (it disassembles the DEX and can
take ten seconds or more on a large APK), all results cached by content hash
(Section 8.5), never by path.
"""

from __future__ import annotations

from pathlib import Path

from droiddesk.core.errors import ApkParseError
from droiddesk.core.models import ApkInfo
from droiddesk.infra.hashing import hash_file


class ApkReader:
    def __init__(self) -> None:
        self._cache: dict[str, ApkInfo] = {}

    def inspect_fast(self, apk_path: Path) -> ApkInfo:
        """pyaxmlparser-backed: package name, version, SDK levels only."""
        file_hash = hash_file(apk_path)
        if file_hash in self._cache:
            return self._cache[file_hash]

        # TODO(Phase 2): from pyaxmlparser import APK; parse manifest-only fields.
        raise NotImplementedError

    def inspect_full(self, apk_path: Path) -> ApkInfo:
        """androguard-backed: manifest, permissions, components, certificates."""
        # TODO(Phase 2): from androguard.core.apk import APK; full analysis.
        raise ApkParseError(f"Full analysis not yet implemented for {apk_path}")

    def extract_string_resources(self, apk_path: Path) -> list[str]:
        """Strings from resources.arsc — where API keys most often live. Used by
        the Privacy Scanner (Section 6.6) and Network Insight's static host
        extraction (Section 6.11).
        """
        # TODO(Phase 4): androguard resources.arsc string pool extraction.
        raise NotImplementedError

    def extract_dex_strings(self, apk_path: Path) -> list[str]:
        """Opt-in deep scan: string constants from the DEX. Slower than resource
        extraction — see Section 6.6.
        """
        # TODO(Phase 4): androguard DEX string constant extraction.
        raise NotImplementedError
