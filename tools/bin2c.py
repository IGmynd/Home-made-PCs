#!/usr/bin/env python3
"""bin -> C-массив: bin2c.py вход.bin выход.h имя"""
import sys

data = open(sys.argv[1], "rb").read()
name = sys.argv[3]
with open(sys.argv[2], "w") as f:
    f.write("/* сгенерировано tools/bin2c.py, руками не править */\n")
    f.write("static const unsigned char %s[] = {\n" % name)
    for i in range(0, len(data), 12):
        f.write("  " + ", ".join("0x%02x" % b for b in data[i:i + 12]) + ",\n")
    f.write("};\nstatic const unsigned int %s_len = %d;\n" % (name, len(data)))