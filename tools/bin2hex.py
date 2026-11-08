#!/usr/bin/env python3
"""bin -> hex для $readmemh: по одному 32-битному слову (little-endian) в строке."""
import struct
import sys

data = open(sys.argv[1], "rb").read()
data += b"\x00" * (-len(data) % 4)
with open(sys.argv[2], "w") as f:
    for (w,) in struct.iter_unpack("<I", data):
        f.write("%08x\n" % w)