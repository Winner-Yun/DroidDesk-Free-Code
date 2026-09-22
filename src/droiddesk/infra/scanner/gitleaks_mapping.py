"""Centralized mapping from Gitleaks RuleID to DroidDesk Severity."""

from __future__ import annotations

from droiddesk.core.severity import Severity

# Explicit mappings for common Gitleaks rule IDs
GITLEAKS_SEVERITY_MAP: dict[str, Severity] = {
    # Critical credentials & server access
    "aws-access-token": Severity.CRITICAL,
    "aws-access-key-id": Severity.CRITICAL,
    "aws-secret-access-key": Severity.CRITICAL,
    "private-key": Severity.CRITICAL,
    "generic-private-key-pem": Severity.CRITICAL,
    "rsa-private-key": Severity.CRITICAL,
    "ssh-private-key": Severity.CRITICAL,
    "dsa-private-key": Severity.CRITICAL,
    "ec-private-key": Severity.CRITICAL,
    "openssh-private-key": Severity.CRITICAL,
    "gcp-service-account": Severity.CRITICAL,
    "google-oauth-client-secret": Severity.CRITICAL,
    "stripe-secret-key": Severity.CRITICAL,
    "github-pat": Severity.CRITICAL,
    "github-oauth": Severity.CRITICAL,
    "slack-app-token": Severity.CRITICAL,
    "slack-bot-token": Severity.CRITICAL,
    "pypi-api-token": Severity.CRITICAL,
    "npm-access-token": Severity.CRITICAL,
    "sendgrid-api-key": Severity.CRITICAL,
    "twilio-api-key": Severity.CRITICAL,
    # High confidence & sensitive client tokens
    "bearer-token": Severity.HIGH,
    "generic-api-key": Severity.HIGH,
    "jwt": Severity.HIGH,
    "artifactory-token": Severity.HIGH,
    "mailchimp-api-key": Severity.HIGH,
    "square-access-token": Severity.HIGH,
    # Low confidence or expected client keys
    "google-api-key": Severity.NEEDS_REVIEW,
    "generic-client-id": Severity.INFORMATIONAL,
}


def get_gitleaks_severity(rule_id: str, description: str = "") -> Severity:
    """Resolve the DroidDesk severity for a Gitleaks finding.

    Uses an exact rule table first, then falls back to keyword heuristics.
    """
    rule_lower = rule_id.lower()
    if rule_lower in GITLEAKS_SEVERITY_MAP:
        return GITLEAKS_SEVERITY_MAP[rule_lower]

    for key, sev in GITLEAKS_SEVERITY_MAP.items():
        if key in rule_lower:
            return sev

    # Keyword heuristics
    desc_lower = description.lower()
    combined = f"{rule_lower} {desc_lower}"
    if any(w in combined for w in ("private", "service-account", "secret")):
        return Severity.CRITICAL
    if any(w in combined for w in ("token", "auth", "password", "jwt")):
        return Severity.HIGH
    if any(w in combined for w in ("key", "credential", "api")):
        return Severity.NEEDS_REVIEW

    return Severity.NEEDS_REVIEW


# Explicit mappings from rule ID to standard uppercase key name
RULE_ID_TO_KEY_NAME: dict[str, str] = {
    # Android specific rules
    "android-firebase-legacy-token": "FIREBASE_API_KEY",
    "firebase-legacy-secret": "FIREBASE_API_KEY",
    "firebase-database-secret": "FIREBASE_DATABASE_SECRET",
    "firebase-api-key": "FIREBASE_API_KEY",
    "android-firebase-api-key": "FIREBASE_API_KEY",
    "firebase-key": "FIREBASE_API_KEY",
    "android-maps-api-key": "GOOGLE_MAPS_API_KEY",
    "google-maps-api-key": "GOOGLE_MAPS_API_KEY",
    "google-map-apk-key": "GOOGLE_MAPS_API_KEY",
    "google-map-api-key": "GOOGLE_MAPS_API_KEY",
    "maps-api-key": "GOOGLE_MAPS_API_KEY",
    "google-api-key": "GOOGLE_API_KEY",
    "android-service-account-json": "GCP_SERVICE_ACCOUNT_KEY",
    "android-signing-key": "ANDROID_SIGNING_KEY",
    "android-env-backend-secret": "BACKEND_SECRET_KEY",
    "android-google-services-json": "GOOGLE_SERVICES_CONFIG",
    # Cloud & Provider credentials
    "aws-access-token": "AWS_ACCESS_TOKEN",
    "aws-access-key-id": "AWS_ACCESS_KEY_ID",
    "aws-secret-access-key": "AWS_SECRET_ACCESS_KEY",
    "gcp-service-account": "GCP_SERVICE_ACCOUNT",
    "google-oauth-client-secret": "GOOGLE_OAUTH_CLIENT_SECRET",
    "stripe-secret-key": "STRIPE_SECRET_KEY",
    "github-pat": "GITHUB_PAT",
    "github-oauth": "GITHUB_OAUTH_TOKEN",
    "slack-app-token": "SLACK_APP_TOKEN",
    "slack-bot-token": "SLACK_BOT_TOKEN",
    "pypi-api-token": "PYPI_API_TOKEN",
    "npm-access-token": "NPM_ACCESS_TOKEN",
    "sendgrid-api-key": "SENDGRID_API_KEY",
    "twilio-api-key": "TWILIO_API_KEY",
    "bearer-token": "BEARER_TOKEN",
    "generic-api-key": "GENERIC_API_KEY",
    "jwt": "JWT_TOKEN",
    "artifactory-token": "ARTIFACTORY_TOKEN",
    "mailchimp-api-key": "MAILCHIMP_API_KEY",
    "square-access-token": "SQUARE_ACCESS_TOKEN",
    "generic-client-id": "CLIENT_ID",
    "private-key": "PRIVATE_KEY",
    "generic-private-key-pem": "PRIVATE_KEY_PEM",
    "rsa-private-key": "RSA_PRIVATE_KEY",
    "ssh-private-key": "SSH_PRIVATE_KEY",
    "dsa-private-key": "DSA_PRIVATE_KEY",
    "ec-private-key": "EC_PRIVATE_KEY",
    "openssh-private-key": "OPENSSH_PRIVATE_KEY",
    "high-entropy-string": "HIGH_ENTROPY_SECRET",
}


def rule_id_to_key_name(rule_id: str) -> str:
    """Convert a scanner rule ID into a normalized, developer-friendly key name.

    Examples:
        - android-firebase-legacy-token -> FIREBASE_API_KEY
        - android-maps-api-key -> GOOGLE_MAPS_API_KEY
        - firebase-api-key -> FIREBASE_API_KEY
        - aws-access-key-id -> AWS_ACCESS_KEY_ID
        - custom-app-secret -> APP_SECRET
        - my-custom-secret -> MY_CUSTOM_SECRET
    """
    rule_lower = rule_id.lower().strip()
    if rule_lower in RULE_ID_TO_KEY_NAME:
        return RULE_ID_TO_KEY_NAME[rule_lower]

    # Clean up prefixes and format to UPPER_SNAKE_CASE
    clean = rule_lower
    for prefix in ("android-", "custom-"):
        if clean.startswith(prefix):
            clean = clean[len(prefix) :]

    # Normalize delimiters
    for ch in ("-", " ", ".", ":", "/"):
        clean = clean.replace(ch, "_")

    # Remove repeated underscores and uppercase
    parts = [p for p in clean.split("_") if p]
    result = "_".join(parts).upper()
    return result or rule_id.upper()
