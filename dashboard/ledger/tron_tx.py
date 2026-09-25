"""Verification and signing of TRC-20 transfers.

TronGrid builds the unsigned transaction for us, but a compromised or malicious API could return one that
pays someone else. So we never sign what we were handed: verify_trc20_transfer() decodes the protobuf that
will actually be hashed and signed and requires it to be *exactly* one TriggerSmartContract call of
transfer(recipient, amount) on our USDT contract from our treasury, with no extra fields.
"""
import hashlib

from eth_keys import keys

from . import tron

TRANSFER_SELECTOR = bytes.fromhex("a9059cbb")  # transfer(address,uint256)
TRIGGER_SMART_CONTRACT = 31


class TxVerificationError(Exception):
    pass


def _varint(buf: bytes, pos: int):
    result = shift = 0
    while True:
        if pos >= len(buf):
            raise TxVerificationError("truncated varint")
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7
        if shift > 63:
            raise TxVerificationError("varint too long")


def _fields(buf: bytes):
    """Yield (field_number, wire_type, value); value is an int (varint) or bytes (length-delimited)."""
    pos = 0
    while pos < len(buf):
        key, pos = _varint(buf, pos)
        field, wire = key >> 3, key & 7
        if wire == 0:
            value, pos = _varint(buf, pos)
        elif wire == 2:
            length, pos = _varint(buf, pos)
            if pos + length > len(buf):
                raise TxVerificationError("truncated field")
            value, pos = buf[pos : pos + length], pos + length
        else:
            raise TxVerificationError(f"unsupported wire type {wire}")
        yield field, wire, value


def transfer_call_data(recipient: str, units: int) -> bytes:
    return TRANSFER_SELECTOR + b"\x00" * 12 + tron.address_to_bytes(recipient)[1:] + units.to_bytes(32, "big")


def transfer_parameter_hex(recipient: str, units: int) -> str:
    """The ABI-encoded arguments (without the 4-byte selector) as TronGrid's `parameter` expects."""
    return transfer_call_data(recipient, units)[4:].hex()


def verify_trc20_transfer(raw_data_hex, tx_id, *, owner, contract, recipient, units, fee_limit_max, now_ms) -> int:
    """Returns the transaction's expiration (ms) or raises TxVerificationError."""
    try:
        raw = bytes.fromhex(raw_data_hex)
    except (ValueError, TypeError):
        raise TxVerificationError("raw_data_hex is not valid hex")
    if hashlib.sha256(raw).hexdigest() != str(tx_id).lower():
        raise TxVerificationError("txID does not match raw_data")

    contracts, expiration, fee_limit = [], None, 0
    for field, wire, value in _fields(raw):
        if field == 11 and wire == 2:
            contracts.append(value)
        elif field == 8 and wire == 0:
            expiration = value
        elif field == 18 and wire == 0:
            fee_limit = value
        elif field in (1, 3, 4, 10, 14):  # ref block, memo, timestamp: harmless
            continue
        else:
            raise TxVerificationError(f"unexpected raw_data field {field}")
    if len(contracts) != 1:
        raise TxVerificationError("transaction must contain exactly one contract")

    contract_type, parameter = None, None
    for field, wire, value in _fields(contracts[0]):
        if field == 1 and wire == 0:
            contract_type = value
        elif field == 2 and wire == 2:
            parameter = value
        else:
            raise TxVerificationError("unexpected contract field")
    if contract_type != TRIGGER_SMART_CONTRACT or parameter is None:
        raise TxVerificationError("not a smart-contract call")

    trigger = None
    for field, wire, value in _fields(parameter):
        if field == 2 and wire == 2:
            trigger = value
        elif not (field == 1 and wire == 2):  # field 1 is the type_url
            raise TxVerificationError("unexpected parameter field")
    if trigger is None:
        raise TxVerificationError("missing contract parameter")

    seen = {}
    for field, wire, value in _fields(trigger):
        if field in seen or field not in (1, 2, 3, 4):
            raise TxVerificationError(f"unexpected or duplicate call field {field}")
        seen[field] = value
    if seen.get(1) != tron.address_to_bytes(owner):
        raise TxVerificationError("owner is not the treasury")
    if seen.get(2) != tron.address_to_bytes(contract):
        raise TxVerificationError("wrong token contract")
    if seen.get(3, 0) != 0:
        raise TxVerificationError("call_value must be zero")
    if seen.get(4) != transfer_call_data(recipient, units):
        raise TxVerificationError("recipient or amount does not match the withdrawal")
    if not 0 < fee_limit <= fee_limit_max:
        raise TxVerificationError("fee_limit missing or above the configured ceiling")
    if expiration is None or expiration <= now_ms:
        raise TxVerificationError("transaction already expired")
    return expiration


class Signer:
    """Holds a private key. Its repr never includes the key."""

    def __init__(self, private_key_hex: str):
        raw = bytes.fromhex(private_key_hex.strip().removeprefix("0x"))
        if len(raw) != 32:
            raise ValueError("private key must be 32 bytes")
        self._key = keys.PrivateKey(raw)
        self.address = tron.address_from_evm_hex(self._key.public_key.to_checksum_address())

    def sign(self, tx_id_hex: str) -> str:
        return self._key.sign_msg_hash(bytes.fromhex(tx_id_hex)).to_bytes().hex()

    def __repr__(self):
        return f"Signer({self.address})"
