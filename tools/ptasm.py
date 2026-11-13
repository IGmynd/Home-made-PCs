#!/usr/bin/env python3
"""Ассемблер байткода ПТ (PTBC v1): ptasm.py программа.pta программа.ptb

Секции: .data и .code. В .data: .byte, .word, .string, .space.
В .code: мнемоники из таблицы OPS. Метки: `имя:`. Комментарии: `;`.
"""
import ast
import re
import struct
import sys

OPS = {
    "halt": 0x00, "push8": 0x01, "push32": 0x02, "dup": 0x03, "drop": 0x04,
    "swap": 0x05, "over": 0x06,
    "add": 0x10, "sub": 0x11, "mul": 0x12, "div": 0x13, "mod": 0x14,
    "and": 0x15, "or": 0x16, "xor": 0x17, "shl": 0x18, "shr": 0x19,
    "sar": 0x1A, "neg": 0x1B, "not": 0x1C,
    "eq": 0x20, "ne": 0x21, "lt": 0x22, "le": 0x23, "gt": 0x24, "ge": 0x25,
    "ld32": 0x30, "st32": 0x31, "ld8": 0x32, "st8": 0x33,
    "jmp": 0x40, "jz": 0x41, "jnz": 0x42, "call": 0x43, "ret": 0x44,
        "sys": 0x50, "trap": 0x51, "alloc": 0x52,
    "frame": 0x60, "leave": 0x61, "ldl": 0x62, "stl": 0x63,
}
NO_ARG = {"halt", "dup", "drop", "swap", "over", "add", "sub", "mul", "div", "mod", "and",
          "or", "xor", "shl", "shr", "sar", "neg", "not", "eq", "ne", "lt", "le", "gt",
          "ge", "ld32", "st32", "ld8", "st8", "ret", "leave", "alloc"}
JUMPS = {"jmp", "jz", "jnz", "call"}
LABEL = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:(.*)$")


class AsmError(Exception):
    pass


def strip_comment(line):
    out, quote = [], None
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == ";":
            break
        else:
            out.append(ch)
    return "".join(out).strip()


def parse_num(tok):
    tok = tok.strip()
    if tok.startswith("'"):
        s = ast.literal_eval(tok)
        if len(s) != 1:
            raise ValueError("символьная константа должна быть из одного символа")
        return ord(s)
    try:
        return int(tok, 0)
    except ValueError:
        return None


def assemble(text):
    labels = {}
    items = []                    # ('code', строка, мнемоника, арг, размер) или ('data', строка, bytes)
    section, code_size, data_size = "code", 0, 0

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = strip_comment(raw)
        while True:
            m = LABEL.match(line)
            if not m:
                break
            name = m.group(1)
            if name in labels:
                raise AsmError(f"строка {lineno}: метка {name} уже определена")
            labels[name] = code_size if section == "code" else data_size
            line = m.group(2).strip()
        if not line:
            continue
        head, _, rest = line.partition(" ")
        head, rest = head.lower(), rest.strip()

        if head in (".data", ".code"):
            section = head[1:]
            continue

        if section == "data":
            if head == ".byte":
                b = bytes(parse_num(x) & 0xFF for x in rest.split(","))
            elif head == ".word":
                b = b"".join(struct.pack("<I", parse_num(x) & 0xFFFFFFFF) for x in rest.split(","))
            elif head == ".string":
                b = ast.literal_eval(rest).encode("latin-1") + b"\x00"
            elif head == ".space":
                b = bytes(parse_num(rest))
            else:
                raise AsmError(f"строка {lineno}: в .data не бывает {head}")
            items.append(("data", lineno, b))
            data_size += len(b)
            continue

        if head not in OPS and head != "push":
            raise AsmError(f"строка {lineno}: неизвестная команда {head}")
        if head == "push":                              # push сам выбирает push8 или push32
            n = parse_num(rest) if rest else None
            head = "push8" if n is not None and -128 <= n <= 127 else "push32"
        if head in NO_ARG:
            size = 1
            if rest:
                raise AsmError(f"строка {lineno}: {head} без аргумента")
        elif head in ("push8", "sys", "trap", "frame", "ldl", "stl"):
            size = 2
        else:
            size = 5
        if head not in NO_ARG and not rest:
            raise AsmError(f"строка {lineno}: {head} требует аргумент")
        items.append(("code", lineno, head, rest, size))
        code_size += size

    code, data = bytearray(), bytearray()
    for it in items:
        if it[0] == "data":
            data += it[2]
            continue
        _, lineno, head, arg, size = it
        code.append(OPS[head])
        if size == 1:
            continue
        val = parse_num(arg)
        if val is None:
            if arg not in labels:
                raise AsmError(f"строка {lineno}: неизвестная метка {arg}")
            val = labels[arg]
        if head == "push8":
            if not -128 <= val <= 127:
                raise AsmError(f"строка {lineno}: {val} не влезает в push8")
            code.append(val & 0xFF)
        elif head in ("sys", "trap", "frame", "ldl", "stl"):
            if not 0 <= val <= 255:
                raise AsmError(f"строка {lineno}: аргумент {head} вне 0..255")
            code.append(val)
        else:
            code += struct.pack("<I", val & 0xFFFFFFFF)

    return b"PTBC" + struct.pack("<HHII", 1, 0, len(code), len(data)) + bytes(code) + bytes(data)


def main():
    if len(sys.argv) != 3:
        sys.exit("использование: ptasm.py вход.pta выход.ptb")
    try:
        img = assemble(open(sys.argv[1], encoding="utf-8").read())
    except AsmError as e:
        sys.exit(f"ошибка: {e}")
    open(sys.argv[2], "wb").write(img)
    print(f"ok: {sys.argv[2]}, {len(img)} байт")


if __name__ == "__main__":
    main()