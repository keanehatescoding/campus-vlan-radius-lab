import verify_configs as v
def test_users_count():
    u = v.parse_users(__import__("pathlib").Path("radius/users"))
    print("count", len(u))
    assert "0200.0000.4001" in u
    assert "020000004001" in u
