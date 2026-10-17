"""Credential export compatibility without modifying or disclosing key files."""
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from scripts import provider_common


@pytest.mark.parametrize('escaped', [False, True])
def test_private_pem_reads_exported_line_endings(tmp_path, monkeypatch, escaped):
    monkeypatch.setattr(provider_common, 'ROOT', tmp_path)
    folder = tmp_path / 'secrets'
    folder.mkdir(mode=0o700)
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(serialization.Encoding.PEM,
                            serialization.PrivateFormat.TraditionalOpenSSL,
                            serialization.NoEncryption())
    original = pem.replace(b'\n', b'\\n') if escaped else pem
    path = folder / 'fixture.pem'
    path.write_bytes(original)
    path.chmod(0o600)
    loaded = serialization.load_pem_private_key(
        provider_common.private_pem({'KEY_PATH': 'secrets/fixture.pem'}, 'KEY_PATH'), None)
    assert loaded.private_numbers() == key.private_numbers()
    assert path.read_bytes() == original
    path.chmod(0o644)
    with pytest.raises(provider_common.SafeError, match='owner only'):
        provider_common.private_pem({'KEY_PATH': 'secrets/fixture.pem'}, 'KEY_PATH')
