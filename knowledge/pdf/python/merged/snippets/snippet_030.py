def test_verify_password_v4_wrong_password_returns_none(random_file_id):
    """Wrong password returns None."""
    o_value = EncryptionUtils.compute_owner_key_v4("owner", "user", 16, 4)
    u_value, _ = EncryptionUtils.compute_user_key_v4(
        "user", o_value, -4, random_file_id, 16, 4
    )

    result = EncryptionUtils.verify_password_v4(
        "wrong", u_value, o_value, -4, random_file_id, 16, 4
    )

    assert result is None, "Wrong password should return None"