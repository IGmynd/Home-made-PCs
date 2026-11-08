#!/usr/bin/env python3
"""Собирает образ носителя ПТ (заголовок из docs/MEDIA.md) и проверяет его."""
import argparse
import struct
import sys
import zlib

SECTOR = 512
MAGIC = b"PTMD"
# magic, версия, класс, флаги, метка, id тома, мин. профиль, (3 байта резерва),
# LBA образа, число секторов, адрес загрузки, точка входа, CRC образа, всего блоков
HDR_FMT = "<4sHBB16sIB3xIIIIII"
CRC_OFF = 0x1FC


def build(args):
    with open(args.kernel, "rb") as f:
        data = f.read()
    nsect = (len(data) + SECTOR - 1) // SECTOR
    data = data.ljust(nsect * SECTOR, b"\x00")
    if 1 + nsect > args.blocks:
        sys.exit("ошибка: образ не влезает в носитель")
    hdr = struct.pack(
        HDR_FMT, MAGIC, 1, args.cls, 1 if args.boot else 0,
        args.label.encode("ascii")[:16], args.volid, args.profile,
        1, nsect, args.load, args.entry, zlib.crc32(data), args.blocks,
    )
    hdr = hdr.ljust(CRC_OFF, b"\x00")
    hdr += struct.pack("<I", zlib.crc32(hdr))
    img = (hdr + data).ljust(args.blocks * SECTOR, b"\x00")
    with open(args.image, "wb") as f:
        f.write(img)
    print(f"ok: {args.image}, секторов образа: {nsect}")


def check(path):
    with open(path, "rb") as f:
        raw = f.read()
    hdr = raw[:SECTOR]
    if hdr[:4] != MAGIC:
        sys.exit("плохой magic")
    if zlib.crc32(hdr[:CRC_OFF]) != struct.unpack_from("<I", hdr, CRC_OFF)[0]:
        sys.exit("CRC заголовка не совпал")
    (_, ver, cls, flags, label, volid, prof,
     lba, nsect, load, entry, icrc, total) = struct.unpack_from(HDR_FMT, hdr)
    body = raw[lba * SECTOR:(lba + nsect) * SECTOR]
    if zlib.crc32(body) != icrc:
        sys.exit("CRC образа не совпал")
    print(f"ok: метка={label.rstrip(bytes(1)).decode()} класс={cls} "
          f"загрузочный={flags & 1} секторов={nsect} вход=0x{entry:08x}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("image")
    p.add_argument("--check", action="store_true")
    p.add_argument("--kernel")
    p.add_argument("--label", default="PT")
    p.add_argument("--cls", type=int, default=1)
    p.add_argument("--boot", action="store_true")
    p.add_argument("--volid", type=int, default=1)
    p.add_argument("--profile", type=int, default=2)
    p.add_argument("--load", type=lambda x: int(x, 0), default=0x80000000)
    p.add_argument("--entry", type=lambda x: int(x, 0), default=0x80000000)
    p.add_argument("--blocks", type=int, default=2880)  # дискета 1.44 МБ
    a = p.parse_args()
    check(a.image) if a.check else build(a)


main()