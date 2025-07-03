import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
import auth_utils


def test_hash_and_verify_pin_success():
    hashed = auth_utils.hash_pin("1234")
    assert hashed != "1234"
    assert auth_utils.verify_pin("1234", hashed)


def test_verify_pin_fail_wrong():
    hashed = auth_utils.hash_pin("1234")
    assert not auth_utils.verify_pin("4321", hashed)


def test_verify_pin_invalid_hash():
    assert not auth_utils.verify_pin("1234", "invalid")
    assert not auth_utils.verify_pin("1234", None)
