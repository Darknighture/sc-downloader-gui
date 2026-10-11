import zstandard

from sc_compression import decompress as _sc_decompress

try:
    import lzham
except ImportError:
    lzham = None


def decompress(data):
    """Decompress Supercell-compressed data.

    Handles the SC version 5 format (little-endian header + Zstd/LZHAM
    payload) which sc_compression 0.6.1 does not support, and falls back to
    sc_compression for everything else (plain text, LZMA, older SC, etc.).
    """
    # SC version 5: "SC" + version(4 LE) + hash_len(4 LE) + hash + payload
    if data[:2] == b'SC':
        version = int.from_bytes(data[2:6], 'little')
        if version >= 5:
            hash_len = int.from_bytes(data[6:10], 'little')
            payload = data[10 + hash_len:]

            if payload[:4] == b'\x28\xb5\x2f\xfd':  # Zstandard
                return zstandard.ZstdDecompressor().decompress(payload)

            if payload[:4] == b'SCLZ' and lzham:  # LZHAM
                dict_size_log2 = payload[4]
                uncompressed_size = int.from_bytes(payload[5:9], 'little')
                return lzham.decompress(
                    payload[9:], uncompressed_size,
                    {'dict_size_log2': dict_size_log2})

            return payload

    decompressed, _signature = _sc_decompress(data)
    return decompressed
