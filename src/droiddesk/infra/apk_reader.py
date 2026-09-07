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

        try:
            from pyaxmlparser import APK
            
            apk = APK(str(apk_path))
            
            info = ApkInfo(
                file_path=apk_path,
                file_hash=file_hash,
                package_name=apk.package,
                version_name=apk.version_name,
                version_code=int(apk.version_code) if apk.version_code else None,
                target_sdk=int(apk.get_target_sdk_version()) if apk.get_target_sdk_version() else None,
                min_sdk=int(apk.get_min_sdk_version()) if apk.get_min_sdk_version() else None,
                size_bytes=apk_path.stat().st_size,
                compile_sdk=None,
            )
            
            self._cache[file_hash] = info
            return info
            
        except Exception as e:
            raise ApkParseError(f"Failed to parse APK {apk_path.name}: {e}") from e

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
