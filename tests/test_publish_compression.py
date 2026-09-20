"""The publish verifier must compare actual encrypted and plaintext byte sizes."""

import importlib.util
from pathlib import Path

from barometer.crypto import envelope


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify_publish", ROOT / "tools" / "verify_publish.py")
assert SPEC and SPEC.loader
verify_publish = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_publish)


def test_compression_ratio_uses_ciphertext_and_utf8_plaintext_bytes(monkeypatch):
    monkeypatch.setattr(envelope, "ITERATIONS", 1000)
    plain = "<section>台股行情資訊</section>" * 1000
    env = envelope.seal(plain, [b"test-only"])
    ratio = verify_publish.compression_ratio(env, plain)
    assert 0 < ratio < 0.5
