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
        import dataclasses
        
        base_info = self.inspect_fast(apk_path)
        
        try:
            from androguard.core.apk import APK
            
            apk = APK(str(apk_path))
            
            signature_schemes = []
            if apk.get_certificates_v1():
                signature_schemes.append(1)
            if apk.get_certificates_v2():
                signature_schemes.append(2)
            if apk.get_certificates_v3():
                signature_schemes.append(3)
            if apk.get_certificates_v31():
                signature_schemes.append(31)
                
            fingerprints = []
            for cert in apk.get_certificates():
                raw_sha = cert.sha256
                if isinstance(raw_sha, bytes):
                    sha_str = raw_sha.hex()
                else:
                    sha_str = str(raw_sha)
                
                sha_str = sha_str.upper()
                # Remove any existing colons just in case, then format
                sha_str = sha_str.replace(":", "")
                formatted = ":".join(sha_str[i:i+2] for i in range(0, len(sha_str), 2))
                fingerprints.append(formatted)
                
            fingerprint_str = ", ".join(fingerprints) if fingerprints else None
            
            enriched_info = dataclasses.replace(
                base_info,
                permissions=apk.get_permissions(),
                activities=apk.get_activities(),
                services=apk.get_services(),
                receivers=apk.get_receivers(),
                providers=apk.get_providers(),
                certificate_fingerprint_sha256=fingerprint_str,
                signature_schemes=signature_schemes,
            )
            
            self._cache[base_info.file_hash] = enriched_info
            return enriched_info
            
        except Exception as e:
            raise ApkParseError(f"Failed to perform full analysis on APK {apk_path.name}: {e}") from e

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
