# tests/fixtures/

## apks/

Small committed sample APKs used by `infra/apk_reader` tests (Section 11): a
normal build, a bundle-derived universal APK, an unsigned APK, and a
deliberately corrupt file. Not yet populated.

## secrets/

Fixture strategy per Section 11 — two directions, both required:

- **Planted credentials** of every rule type in `infra/scanner/rules.toml` and
  `android.toml`, which must all be detected.
- **Realistic false-positive candidates** — UUIDs, git SHAs, base64 images,
  minified bundles, legitimate Maps API keys — which must produce either no
  finding or a correctly classified low-severity one.

A rule change that improves recall while quietly destroying precision should be
caught by this suite immediately. Not yet populated.
