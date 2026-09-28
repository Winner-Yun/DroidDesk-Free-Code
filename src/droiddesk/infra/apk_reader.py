"""APK reader providing metadata inspection, manifest parsing, and string extraction."""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

from droiddesk.core.errors import ApkParseError
from droiddesk.core.models import ApkInfo
from droiddesk.infra.hashing import hash_file
from droiddesk.infra.process import ProcessRunner
from droiddesk.infra.tools import ToolLocator


@dataclasses.dataclass(slots=True)
class _ParsedSignature:
    signature_schemes: list[int]
    signature_verified: bool
    certificate_dn: str | None
    certificate_fingerprint_sha256: str | None
    certificate_fingerprint_sha1: str | None
    certificate_fingerprint_md5: str | None
    signature_source: str


class ApkReader:
    def __init__(
        self,
        tool_locator: ToolLocator | None = None,
        process_runner: ProcessRunner | None = None,
    ) -> None:
        self._cache: dict[str, ApkInfo] = {}
        self._tool_locator = tool_locator
        self._process_runner = process_runner

    def inspect_fast(self, apk_path: Path) -> ApkInfo:
        """pyaxmlparser-backed: package name, version, SDK levels only."""
        file_hash = hash_file(apk_path)
        if file_hash in self._cache:
            return self._cache[file_hash]

        try:
            from pyaxmlparser import APK  # type: ignore[import-untyped]

            apk = APK(str(apk_path))

            debuggable: bool | None = False
            try:
                manifest_xml = apk.get_android_manifest_xml()
                if manifest_xml is not None:
                    app_elem = manifest_xml.find("application")
                    if app_elem is not None:
                        dbg_attr = app_elem.get(
                            "{http://schemas.android.com/apk/res/android}debuggable"
                        )
                        if dbg_attr is not None:
                            debuggable = str(dbg_attr).lower() in ("true", "1")
            except Exception:
                debuggable = None

            perms: list[str] = []
            try:
                perms = list(apk.get_permissions() or [])
            except Exception:
                pass

            activities: list[str] = []
            try:
                activities = list(apk.get_activities() or [])
            except Exception:
                pass

            services: list[str] = []
            try:
                services = list(apk.get_services() or [])
            except Exception:
                pass

            receivers: list[str] = []
            try:
                receivers = list(apk.get_receivers() or [])
            except Exception:
                pass

            providers: list[str] = []
            try:
                providers = list(apk.get_providers() or [])
            except Exception:
                pass

            info = ApkInfo(
                file_path=apk_path,
                file_hash=file_hash,
                package_name=apk.package,
                version_name=apk.version_name,
                version_code=int(apk.version_code) if apk.version_code else None,
                target_sdk=(
                    int(apk.get_target_sdk_version()) if apk.get_target_sdk_version() else None
                ),
                min_sdk=int(apk.get_min_sdk_version()) if apk.get_min_sdk_version() else None,
                size_bytes=apk_path.stat().st_size,
                compile_sdk=None,
                debuggable=debuggable,
                permissions=perms,
                activities=activities,
                services=services,
                receivers=receivers,
                providers=providers,
            )

            self._cache[file_hash] = info
            return info

        except Exception as e:
            raise ApkParseError(f"Failed to parse APK {apk_path.name}: {e}") from e

    def _inspect_signature_apksigner(self, apk_path: Path) -> _ParsedSignature | None:
        """Run `apksigner verify --print-certs -v` command to get real signature details."""
        if not self._tool_locator:
            return None

        try:
            apksigner_path = self._tool_locator.resolve("apksigner")
        except Exception:
            return None

        runner = self._process_runner or ProcessRunner()
        env = self._tool_locator.execution_env()

        try:
            result = runner.run(
                apksigner_path,
                ["verify", "--print-certs", "-v", str(apk_path)],
                timeout=15.0,
                env=env,
            )
        except Exception:
            return None

        stdout = result.stdout
        if not stdout:
            return None

        schemes: list[int] = []
        if re.search(r"Verified using v1 scheme.*:\s*true", stdout, re.IGNORECASE):
            schemes.append(1)
        if re.search(r"Verified using v2 scheme.*:\s*true", stdout, re.IGNORECASE):
            schemes.append(2)
        if re.search(r"Verified using v3 scheme.*:\s*true", stdout, re.IGNORECASE):
            schemes.append(3)
        if re.search(r"Verified using v3\.1 scheme.*:\s*true", stdout, re.IGNORECASE):
            schemes.append(31)
        if re.search(r"Verified using v4 scheme.*:\s*true", stdout, re.IGNORECASE):
            schemes.append(4)

        verified = bool(re.search(r"^Verifies\b", stdout, re.MULTILINE))

        def format_hex(h: str) -> str:
            clean = h.strip().replace(":", "").upper()
            return ":".join(clean[i : i + 2] for i in range(0, len(clean), 2))

        sha256_match = re.search(r"certificate SHA-256 digest:\s*([0-9a-fA-F]+)", stdout)
        sha1_match = re.search(r"certificate SHA-1 digest:\s*([0-9a-fA-F]+)", stdout)
        md5_match = re.search(r"certificate MD5 digest:\s*([0-9a-fA-F]+)", stdout)
        dn_match = re.search(r"certificate DN:\s*(.+)", stdout)

        return _ParsedSignature(
            signature_schemes=schemes,
            signature_verified=verified,
            certificate_dn=dn_match.group(1).strip() if dn_match else None,
            certificate_fingerprint_sha256=(
                format_hex(sha256_match.group(1)) if sha256_match else None
            ),
            certificate_fingerprint_sha1=(format_hex(sha1_match.group(1)) if sha1_match else None),
            certificate_fingerprint_md5=(format_hex(md5_match.group(1)) if md5_match else None),
            signature_source="apksigner",
        )

    def inspect_full(self, apk_path: Path) -> ApkInfo:
        """Full analysis: manifest, permissions, components via androguard, plus
        cryptographic signature verification via `apksigner` command.
        """
        base_info = self.inspect_fast(apk_path)

        # Attempt official apksigner command first (very fast, no bytecode parsing)
        sig_info = self._inspect_signature_apksigner(apk_path)

        if sig_info is not None:
            enriched_info = dataclasses.replace(
                base_info,
                certificate_fingerprint_sha256=sig_info.certificate_fingerprint_sha256,
                certificate_fingerprint_sha1=sig_info.certificate_fingerprint_sha1,
                certificate_fingerprint_md5=sig_info.certificate_fingerprint_md5,
                certificate_dn=sig_info.certificate_dn,
                signature_verified=sig_info.signature_verified,
                signature_schemes=sig_info.signature_schemes,
                signature_source=sig_info.signature_source,
            )
            self._cache[base_info.file_hash] = enriched_info
            return enriched_info

        try:
            from androguard.core.apk import APK  # type: ignore[import-untyped]

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
                sha1_fingerprints = []
                dns = []
                for cert in apk.get_certificates():
                    raw_sha = cert.sha256
                    sha_str = raw_sha.hex() if isinstance(raw_sha, bytes) else str(raw_sha)
                    sha_str = sha_str.upper().replace(":", "")
                    formatted = ":".join(sha_str[i : i + 2] for i in range(0, len(sha_str), 2))
                    fingerprints.append(formatted)

                    raw_sha1 = getattr(cert, "sha1", None)
                    if raw_sha1:
                        sha1_hex = raw_sha1.hex() if isinstance(raw_sha1, bytes) else str(raw_sha1)
                        sha1_hex = sha1_hex.upper().replace(":", "")
                        sha1_fingerprints.append(
                            ":".join(sha1_hex[i : i + 2] for i in range(0, len(sha1_hex), 2))
                        )

                    subj = getattr(cert, "subject", None)
                    if subj:
                        hf = getattr(subj, "human_friendly", None)
                        dns.append(str(hf) if hf else str(subj))

                fingerprint_str = ", ".join(fingerprints) if fingerprints else None
                sha1_str = ", ".join(sha1_fingerprints) if sha1_fingerprints else None
                md5_str = None
                cert_dn = ", ".join(dns) if dns else None
                sig_verified = bool(signature_schemes)
                sig_source = "androguard"

            enriched_info = dataclasses.replace(
                base_info,
                permissions=list(apk.get_permissions() or base_info.permissions),
                activities=list(apk.get_activities() or base_info.activities),
                services=list(apk.get_services() or base_info.services),
                receivers=list(apk.get_receivers() or base_info.receivers),
                providers=list(apk.get_providers() or base_info.providers),
                certificate_fingerprint_sha256=fingerprint_str,
                certificate_fingerprint_sha1=sha1_str,
                certificate_fingerprint_md5=md5_str,
                certificate_dn=cert_dn,
                signature_verified=sig_verified,
                signature_schemes=signature_schemes,
                signature_source=sig_source,
            )

            self._cache[base_info.file_hash] = enriched_info
            return enriched_info

        except Exception:
            return base_info

    def get_manifest_xml(self, apk_path: Path) -> str:
        """Extract and format AndroidManifest.xml from an APK."""
        import xml.dom.minidom as minidom
        import xml.etree.ElementTree as ET

        try:
            from pyaxmlparser import APK as PyAxmlAPK

            apk = PyAxmlAPK(str(apk_path))
            elem = apk.get_android_manifest_xml()
            if elem is not None:
                raw_bytes = ET.tostring(elem, encoding="utf-8")
                dom = minidom.parseString(raw_bytes)
                pretty = dom.toprettyxml(indent="  ")
                lines = [line for line in pretty.splitlines() if line.strip()]
                return "\n".join(lines)
        except Exception:
            pass

        try:
            from androguard.core.apk import APK as AndroAPK

            apk = AndroAPK(str(apk_path))
            elem = apk.get_android_manifest_xml()
            if elem is not None:
                raw_bytes = ET.tostring(elem, encoding="utf-8")
                dom = minidom.parseString(raw_bytes)
                pretty = dom.toprettyxml(indent="  ")
                lines = [line for line in pretty.splitlines() if line.strip()]
                return "\n".join(lines)
        except Exception:
            pass

        return "<!-- AndroidManifest.xml could not be decoded -->"

    def get_archive_entries(self, apk_path: Path) -> list[dict[str, object]]:
        """Extract file listing and size statistics from the APK zip archive."""
        import zipfile

        if not apk_path.is_file():
            return []

        entries: list[dict[str, object]] = []
        try:
            with zipfile.ZipFile(apk_path, "r") as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    entries.append(
                        {
                            "name": info.filename,
                            "file_size": info.file_size,
                            "compress_size": info.compress_size,
                        }
                    )
        except Exception:
            pass
        return entries


    def extract_named_string_resources(self, apk_path: Path) -> list[tuple[str, str]]:
        """Extract (name, value) string resource pairs from resources.arsc."""
        try:
            from androguard.core.apk import APK

            apk = APK(str(apk_path))
            arsc = apk.get_android_resources()
            if not arsc:
                return []
            named_strings: list[tuple[str, str]] = []
            seen: set[tuple[str, str]] = set()
            for pkg in arsc.get_packages_names():
                resolved = arsc.get_resolved_strings()
                if resolved and pkg in resolved:
                    for _locale, res_dict in resolved[pkg].items():
                        for res_id, val in res_dict.items():
                            if isinstance(val, str) and val:
                                item = (str(res_id), val)
                                if item not in seen:
                                    seen.add(item)
                                    named_strings.append(item)
            return named_strings
        except Exception:
            return []

    def extract_string_resources(self, apk_path: Path) -> list[str]:
        """Extract compiled string resources from resources.arsc."""
        return list(dict.fromkeys(val for _, val in self.extract_named_string_resources(apk_path)))

    def extract_dex_strings(self, apk_path: Path) -> list[str]:
        """Extract string constants from DEX bytecode."""
        try:
            from androguard.core.apk import APK
            from androguard.core.dex import DEX  # type: ignore[import-untyped]

            apk = APK(str(apk_path))
            all_strings: list[str] = []
            for dex_bytes in apk.get_all_dex():
                dex = DEX(dex_bytes)
                all_strings.extend(dex.get_strings())
            return list(dict.fromkeys(all_strings))
        except Exception:
            return []
