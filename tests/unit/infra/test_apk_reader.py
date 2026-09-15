from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from droiddesk.infra.apk_reader import ApkReader
from droiddesk.infra.process import ProcessResult

_SAMPLE_APKSIGNER_OUTPUT = (
    "Verifies\n"
    "Verified using v1 scheme (JAR signing): false\n"
    "Verified using v2 scheme (APK Signature Scheme v2): true\n"
    "Verified using v3 scheme (APK Signature Scheme v3): false\n"
    "Verified using v3.1 scheme (APK Signature Scheme v3.1): false\n"
    "Verified using v4 scheme (APK Signature Scheme v4): false\n"
    "Verified for SourceStamp: false\n"
    "Number of signers: 1\n"
    "Signer #1 certificate DN: C=US, O=Android, CN=Android Debug\n"
    "Signer #1 certificate SHA-256 digest: "
    "9f8d1a1294cb7a34595c0b6074571cb1b9e124a739449a152304a91b658de25c\n"
    "Signer #1 certificate SHA-1 digest: 13c613578d73fb0a254c7b174927b488c2d8b579\n"
    "Signer #1 certificate MD5 digest: 665043dffd5cd3b3e20943446dcdd572\n"
    "Signer #1 key algorithm: RSA\n"
    "Signer #1 key size (bits): 2048\n"
)


def test_apk_reader_inspect_signature_apksigner(tmp_path: Path) -> None:
    apk_file = tmp_path / "sample.apk"
    apk_file.write_bytes(b"PK\x03\x04fake_apk_content")

    tool_locator = MagicMock()
    tool_locator.resolve.return_value = Path("C:/Android/sdk/build-tools/35.0.1/apksigner.bat")
    tool_locator.execution_env.return_value = {}

    process_runner = MagicMock()
    process_runner.run.return_value = ProcessResult(
        exit_code=0,
        stdout=_SAMPLE_APKSIGNER_OUTPUT,
        stderr="",
    )

    reader = ApkReader(tool_locator=tool_locator, process_runner=process_runner)
    sig = reader._inspect_signature_apksigner(apk_file)

    assert sig is not None
    assert sig.signature_schemes == [2]
    assert sig.signature_verified is True
    assert sig.certificate_dn == "C=US, O=Android, CN=Android Debug"
    assert sig.certificate_fingerprint_sha256 == (
        "9F:8D:1A:12:94:CB:7A:34:59:5C:0B:60:74:57:1C:B1:B9:E1:24:A7:39:44:9A:15:23:04:A9:1B:65:8D:E2:5C"
    )
    assert sig.certificate_fingerprint_sha1 == (
        "13:C6:13:57:8D:73:FB:0A:25:4C:7B:17:49:27:B4:88:C2:D8:B5:79"
    )
    assert sig.certificate_fingerprint_md5 == "66:50:43:DF:FD:5C:D3:B3:E2:09:43:44:6D:CD:D5:72"
    assert sig.signature_source == "apksigner"


def test_apk_reader_inspect_signature_fails_gracefully(tmp_path: Path) -> None:
    apk_file = tmp_path / "broken.apk"
    apk_file.write_bytes(b"dummy")

    tool_locator = MagicMock()
    tool_locator.resolve.side_effect = Exception("Tool not found")

    reader = ApkReader(tool_locator=tool_locator)
    sig = reader._inspect_signature_apksigner(apk_file)
    assert sig is None
