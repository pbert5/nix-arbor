from pathlib import Path

from backend.catalog_security import ensure_keypair, get_keys_dir, get_private_key_path, get_public_key_path


def test_catalog_signing_keys_follow_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("FOSSILSAFE_DATA_DIR", str(tmp_path))

    public_pem, key_id = ensure_keypair()

    assert public_pem.startswith("-----BEGIN PUBLIC KEY-----")
    assert key_id.startswith("appliance_key_")
    assert get_keys_dir() == tmp_path / "keys"
    assert get_private_key_path() == tmp_path / "keys" / "appliance.key"
    assert get_public_key_path() == tmp_path / "keys" / "appliance.pub"
    assert Path(get_private_key_path()).exists()
    assert Path(get_public_key_path()).exists()