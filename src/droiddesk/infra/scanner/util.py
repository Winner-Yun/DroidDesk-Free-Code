"""Shared scanner utilities: hashing and secret redaction."""

from __future__ import annotations

from pathlib import Path

import xxhash


def hash_match(text: str) -> str:
    """Compute a deterministic hash of a matched secret or line."""
    return xxhash.xxh3_64(text.encode("utf-8")).hexdigest()


def redact_secret(text: str, keep: int = 4) -> str:
    """Return the full secret string without redaction or masking so users can inspect it."""
    return text


def detect_environment_info(file_path: Path, rule_id: str | None = None) -> tuple[str, str]:
    """Return (short_tag, detailed_description) for a finding's environment and file context.

    Examples:
        - .env.production -> ("Production Env", "Production Environment Config (.env.production)")
        - Config.java -> ("Java Source", "Java Application Source Code (Config.java)")
        - AndroidManifest.xml -> ("Android Manifest", "Android Application Manifest")
    """
    name = file_path.name.lower()
    posix = file_path.as_posix().lower()
    ext = file_path.suffix.lower()

    # Environment files (.env)
    if name.startswith(".env"):
        if "prod" in name:
            return ("Production Env", "Production Environment Config")
        if "stag" in name:
            return ("Staging Env", "Staging Environment Config")
        if any(x in name for x in ("local", "dev")):
            return ("Development Env", "Local / Development Environment")
        return ("Environment Config", "Root Environment Variables")
    if name in ("local.properties", "gradle.properties"):
        return ("Properties Config", "Project Properties File")

    # Android Manifest and XML resources
    if name == "androidmanifest.xml":
        return ("Android Manifest", "Android Application Manifest")
    if name == "resources.arsc":
        return ("Android Resource", "Compiled Resource Table (strings.xml)")
    if ext == ".xml":
        if "values" in posix or "strings" in name or "secrets" in name:
            return ("Android Resource", "Android XML Resource")
        if "res/" in posix:
            return ("Android Resource", "Android Resource File")
        return ("XML Config", "XML Configuration")

    # Google and cloud service configurations
    if name == "google-services.json":
        return ("Google Services", "Firebase / Google Cloud Client Config")
    if "service-account" in name or "service_account" in name:
        return ("Service Account", "GCP Service Account Credentials")

    # Keystores and certificates
    if ext in (".jks", ".keystore", ".p12", ".pkcs12", ".bks"):
        return ("Signing Keystore", "Android Signing Keystore")
    if ext in (".pem", ".key", ".crt", ".der"):
        return ("Certificate / Key", "Cryptographic Key / Certificate")

    # Build configuration and CI/CD pipelines
    if name in ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"):
        return ("Build Script", "Gradle Build Script")
    if name == "pom.xml":
        return ("Build Script", "Maven POM File")
    if ".github" in posix or ".gitlab-ci" in posix or "jenkins" in name:
        return ("CI/CD Pipeline", "CI/CD Workflow Pipeline")

    # Source code
    if ext == ".java":
        return ("Java Source", "Java Application Source Code")
    if ext in (".kt", ".kts"):
        return ("Kotlin Source", "Kotlin Application Source Code")
    if ext in (".c", ".cpp", ".cc", ".cxx", ".h", ".hpp"):
        return ("Native C/C++", "Native NDK / C++ Source Code")
    if ext == ".py":
        return ("Python Script", "Python Source File")
    if ext in (".js", ".jsx", ".ts", ".tsx"):
        return ("JS / TS Source", "JavaScript / TypeScript")
    if ext == ".dart":
        return ("Dart Source", "Flutter / Dart Source Code")
    if ext == ".json":
        return ("JSON Config", "JSON Configuration File")

    # APK archive contents
    if ".apk" in posix or posix.startswith("assets/") or posix.startswith("res/"):
        return ("APK Archive", "Compiled APK Asset / Resource")

    return ("Source File", "Project File")
