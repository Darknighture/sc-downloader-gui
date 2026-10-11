"""Supercell asset decompression helpers.

The decoders live here instead of in a third-party package: the formats the
downloader has to handle are few and well understood, and every branch below
was checked against real assets fetched from the live CDN.

Container formats that are recognised:

============================  ==============================================
``SC`` v5                     ``SC`` + version (4 bytes LE) + hash_len
                              (4 bytes LE) + hash + payload
``SC`` v1-v4                  ``SC`` + version (4 bytes BE) [+ a second
                              version field when the first is >= 4] +
                              hash_len (4 bytes BE) + hash + payload
``SCLZ``                      ``SCLZ`` + dict_size_log2 (1 byte) +
                              uncompressed_size (4 bytes LE) + LZHAM stream
Zstandard                     the ``28 B5 2F FD`` frame magic
LZMA                          props (1 byte) + dict_size (4 bytes LE) +
                              uncompressed_size (4 bytes LE) + marker
                              (1 byte) + stream
``Sig:``                      ``Sig:`` + 68 byte header + another container
============================  ==============================================

Anything else - a PNG, or an ``.sc`` texture that is already decompressed - is
returned untouched.

LZHAM is the only codec that is not implemented here, because a pure Python
decoder for it would be unreasonably slow. It falls back, in order, to:

1. the native ``pylzham`` extension, when installed;
2. the ``lzham.exe`` bundled inside the optional ``sc-compression`` package
   (Windows only);
3. a :class:`ValueError`, so the caller keeps the compressed bytes rather
   than writing a truncated file.
"""

import lzma
import re
import sys

import zstandard

try:
    import lzham as _lzham_native
except ImportError:
    _lzham_native = None

# sc_compression bundles a command line lzham binary but only wires it up on
# Windows, so mirror that guard here. The package is optional.
_lzham_exe = None
if sys.platform == 'win32':
    try:
        from sc_compression.support.lzham import LZHAM as _lzham_exe
    except ImportError:
        _lzham_exe = None

ZSTD_MAGIC = b'\x28\xb5\x2f\xfd'
LZHAM_MAGIC = b'SCLZ'
SIG_MAGIC = b'Sig:'

#: LZMA containers start with a normal LZMA properties byte followed by a
#: dictionary size and an uncompressed size. Two zero bytes right after the
#: properties byte is what identifies them.
LZMA_MAGIC = re.compile(b'\x00\x00?\x00')

#: Bytes skipped after ``Sig:`` before the wrapped container starts.
SIG_HEADER_SIZE = 68

#: Largest container nesting that is considered sane (SC -> Sig: -> SC ...).
MAX_NESTING = 4


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
        'no LZHAM decoder available - install pylzham, or the optional '
        'sc-compression package (see README, "LZHAM support")')


def _decompress_lzma(data):
    """Decode an LZMA container.

    The container stores the uncompressed size as 4 bytes, but the LZMA
    "alone" header wants 8. Supplying the real value is not optional: these
    streams carry no end-of-stream marker, and when liblzma is told the size
    is unknown it either rejects the stream as corrupt or - worse - decodes
    the trailing padding and appends the resulting garbage. The 8 x 0xFF
    "unknown" spelling is only used when the size field is empty.

    Both behaviours were reproduced against assets taken from the live CDN and
    cross-checked byte for byte with an independent decoder.
    """
    uncompressed_size = int.from_bytes(data[5:9], 'little')

    if uncompressed_size > 0:
        header = data[:5] + uncompressed_size.to_bytes(8, 'little')
    else:
        header = data[:5] + b'\xff' * 8

    return lzma.LZMADecompressor().decompress(header + data[9:])


def _split_sc_container(data):
    """Strip an ``SC`` header and return its payload, or ``None``.

    Two dialects exist and they are told apart by reading the version field
    both ways: current assets store it little-endian with a small value, older
    ones store it big-endian. A big-endian version read little-endian gives a
    number in the millions, so the two can never be confused.
    """
    little_version = int.from_bytes(data[2:6], 'little')

    if 1 <= little_version <= 0xFFFF:
        # "SC" + version (4 LE) + hash_len (4 LE) + hash
        start = 10
        hash_length = int.from_bytes(data[6:10], 'little')
    else:
        big_version = int.from_bytes(data[2:6], 'big')
        if not 1 <= big_version <= 0xFFFF:
            return None

        if big_version >= 4:
            # A version 4+ header carries the real version in a second field.
            inner_version = int.from_bytes(data[6:10], 'big')
            if not 1 <= inner_version <= 0xFFFF:
                return None
            start = 14
        else:
            start = 10

        hash_length = int.from_bytes(data[start - 4:start], 'big')

    if len(data) < start + hash_length:
        return None

    return data[start + hash_length:]


def decompress(data):
    """Decompress Supercell-compressed data.

    The container wrappers are peeled off one at a time until something
    recognisable is left. Unrecognised input - including data that is already
    decompressed - is returned unchanged, so this is safe to call on every
    downloaded file.
    """
    for _ in range(MAX_NESTING):
        if data.startswith(LZHAM_MAGIC):
            return _decompress_lzham(data)

        if data.startswith(b'SC'):
            payload = _split_sc_container(data)
            if payload is None:
                return data
            data = payload
            continue

        if data.startswith(SIG_MAGIC):
            data = data[SIG_HEADER_SIZE:]
            continue

        if len(data) >= 5 and LZMA_MAGIC.match(data[1:5]):
            return _decompress_lzma(data)

        if data.startswith(ZSTD_MAGIC):
            return zstandard.ZstdDecompressor().decompress(data)

        return data

    raise ValueError('SC container nesting is deeper than {} levels'.format(MAX_NESTING))
