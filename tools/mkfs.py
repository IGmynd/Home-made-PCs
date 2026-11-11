#!/usr/bin/env python3
"""Собирает образ файловой системы PTFS v1: mkfs.py выход.img файл1 файл2 ... (до 15 файлов).

Раскладка (секторы по 512 байт, номера от начала образа):
  сектор 0: каталог (32 байта заголовок + до 15 записей по 32 байта)
  сектор 1...: файлы подряд, каждый выровнен по сектору
Запись каталога: имя[16] (с нулями), начало (сектор), размер (байт), CRC32, тип, 3 байта резерва.
Тип по расширению: .ptb = 1 (байткод), .txt = 2 (текст), остальное 0 (данные).
"""
import os
import struct
import sys
import zlib

SECTOR = 512
TYPES = {".ptb": 1, ".txt": 2}


def main():
    if len(sys.argv) < 3:
        sys.exit("использование: mkfs.py выход.img файл...")
    out, files = sys.argv[1], sys.argv[2:]
    if len(files) > 15:
        sys.exit("ошибка: не больше 15 файлов")

    entries, body, sector, seen = [], b"", 1, set()
    for path in files:
        name = os.path.basename(path)
        raw = name.encode("ascii")
        if not 0 < len(raw) <= 15:
            sys.exit(f"ошибка: имя {name!r} должно быть от 1 до 15 символов")
        if name in seen:
            sys.exit(f"ошибка: имя {name} повторяется")
        seen.add(name)
        data = open(path, "rb").read()
        ftype = TYPES.get(os.path.splitext(name)[1].lower(), 0)
        entries.append(struct.pack("<16sIIIB3x", raw, sector, len(data), zlib.crc32(data), ftype))
        n = (len(data) + SECTOR - 1) // SECTOR
        body += data.ljust(n * SECTOR, b"\x00")
        sector += n

    directory = b"PTFS" + struct.pack("<HH", 1, len(entries)) + bytes(24) + b"".join(entries)
    img = directory.ljust(SECTOR, b"\x00") + body
    open(out, "wb").write(img)
    print(f"ok: {out}, файлов: {len(entries)}, секторов: {sector}")


main()