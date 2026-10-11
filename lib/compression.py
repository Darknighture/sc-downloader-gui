"""Supercell asset decompression helpers.

Supercell ships its assets in a few different containers. This module knows
enough about the "SC version 5" container (little-endian header + Zstd or
LZHAM payload) to handle it directly, and delegates every other format
(plain text, LZMA, older SC versions, ...) to ``sc_compression``.

LZHAM decoding has three tiers, in order of preference:

1. the native ``pylzham`` extension, when installed;
2. the ``lzham.exe`` bundled inside ``sc_compression`` (Windows only);
3. otherwise a :class:`ValueError`, so the caller can keep the compressed
   bytes instead of writing a truncated file.
"""

import sys

import zstandard

from sc_compression import decompress as _sc_decompress

try:
    import lzham as _lzham_native
except ImportError:
    _lzham_native = None

# sc_compression bundles a command line lzham binary but only wires it up on
# Windows, so mirror that guard here.
_lzham_exe = None
if sys.platform == 'win32':
    try:
        from sc_compression.support.lzham import LZHAM as _lzham_exe
    except ImportError:
        _lzham_exe = None

ZSTD_MAGIC = b'\x28\xb5\x2f\xfd'
LZHAM_MAGIC = b'SCLZ'


def lzham_available():
    """True when LZHAM payloads can be decoded in this environment."""
    return _lzham_native is not None or _lzham_exe is not None


def _decompress_lzham(payload):
    """Decode an ``SCLZ`` payload.

    Layout: ``SCLZ`` + dict_size_log2 (1 byte) + uncompressed_size (4 bytes LE)
    + the raw LZHAM stream.
    """
    filters = {'dict_size_log2': payload[4]}
    uncompressed_size = int.from_bytes(payload[5:9], 'little')
    stream = payload[9:]

    if _lzham_native is not None:
        return _lzham_native.decompress(stream, uncompressed_size, filters)

    if _lzham_exe is not None:
        decompressed = _lzham_exe.decompress(stream, uncompressed_size, filters)
        if decompressed is not None:
            return decompressed
        raise ValueError('the bundled lzham decoder failed')

    raise ValueError(
        'no LZHAM decoder available - install pylzham (see README, "LZHAM support")')


def decompress(data):
    """Decompress Supercell-compressed data.

    Handles the SC version 5 format (little-endian header + Zstd/LZHAM
    payload) directly, and falls back to sc_compression for everything else
    (plain text, LZMA, older SC, etc.).
    """
    # SC version 5: "SC" + version(4 LE) + hash_len(4 LE) + hash + payload
    if data[:2] == b'SC':
        version = int.from_bytes(data[2:6], 'little')
        if version >= 5:
            hash_len = int.from_bytes(data[6:10], 'little')
            payload = data[10 + hash_len:]

            if payload[:4] == ZSTD_MAGIC:  # Zstandard
                return zstandard.ZstdDecompressor().decompress(payload)

            if payload[:4] == LZHAM_MAGIC:  # LZHAM
                return _decompress_lzham(payload)

            # A v5 container with an uncompressed payload: hand the bytes
            # through untouched rather than dropping the content.
            return payload

    decompressed, _signature = _sc_decompress(data)
    return decompressed
