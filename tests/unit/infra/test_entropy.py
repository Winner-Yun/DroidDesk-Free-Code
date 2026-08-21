from droiddesk.infra.scanner.entropy import is_known_benign_shape, looks_like_credential


def test_high_entropy_value_on_credential_named_variable_flags() -> None:
    value = "k3f9Z2mQ8xL1vN7pR4tY6wA0bC5dE9gH2jK4mP7qS1u"
    assert looks_like_credential("api_secret", value)


def test_short_value_does_not_flag_regardless_of_name() -> None:
    assert not looks_like_credential("secret", "tooshort")


def test_non_credential_variable_name_does_not_flag() -> None:
    value = "k3f9Z2mQ8xL1vN7pR4tY6wA0bC5dE9gH2jK4mP7qS1u"
    assert not looks_like_credential("greeting_message", value)


def test_uuid_is_known_benign_shape() -> None:
    assert is_known_benign_shape("550e8400-e29b-41d4-a716-446655440000")


def test_sha256_hex_is_known_benign_shape() -> None:
    assert is_known_benign_shape("a" * 64)
