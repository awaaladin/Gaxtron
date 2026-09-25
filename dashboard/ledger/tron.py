"""TRON address helpers (base58check, no third-party dependency).

A TRON address is base58check(0x41 || last 20 bytes of keccak256(pubkey)), which is the same 20 bytes
as the Ethereum address for the same key — so eth_account can generate the keypair.
"""
import hashlib

_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_INDEX = {c: i for i, c in enumerate(_ALPHABET)}
ADDRESS_PREFIX = 0x41
# 41 followed by 20 zero bytes: funds sent here are unrecoverable.
BURN_ADDRESS = "T9yD14Nj9j7xAB4dbGeiX9h8unkKHxuWwb"


def _checksum(payload: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]


def b58encode(data: bytes) -> str:
    number = int.from_bytes(data, "big")
    out = ""
    while number:
        number, rem = divmod(number, 58)
        out = _ALPHABET[rem] + out
    return "1" * (len(data) - len(data.lstrip(b"\x00"))) + out


def b58decode(text: str) -> bytes:
    number = 0
    for char in text:
        number = number * 58 + _INDEX[char]
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big")
    return b"\x00" * (len(text) - len(text.lstrip("1"))) + raw


def address_to_bytes(address: str) -> bytes:
    """21-byte payload (0x41 + 20 bytes). Raises ValueError unless the address is valid."""
    if not isinstance(address, str) or len(address) != 34 or address[0] != "T":
        raise ValueError("not a TRON address")
    try:
        raw = b58decode(address)
    except KeyError as exc:
        raise ValueError("invalid base58 character") from exc
    if len(raw) != 25 or raw[0] != ADDRESS_PREFIX or raw[21:] != _checksum(raw[:21]):
        raise ValueError("bad TRON address checksum")
    return raw[:21]


def is_valid_address(address: str) -> bool:
    try:
        address_to_bytes(address)
    except ValueError:
        return False
    return True


def bytes_to_address(payload: bytes) -> str:
    if len(payload) != 21 or payload[0] != ADDRESS_PREFIX:
        raise ValueError("payload must be 21 bytes starting with 0x41")
    return b58encode(payload + _checksum(payload))


def address_from_evm_hex(evm_address: str) -> str:
    return bytes_to_address(bytes([ADDRESS_PREFIX]) + bytes.fromhex(evm_address.removeprefix("0x")))
