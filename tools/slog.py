#!/usr/bin/env python3
"""Компилятор языка «Слог» в ассемблер байткода ПТ.

    slog.py программа.sl программа.pta

Язык похож на Питон, но все ключевые слова и имена по-русски (латиница в именах запрещена).
Состоит из модулей: slog_lex (лексер), slog_parse (разборщик), slog_link (подключение модулей),
slog_types (вывод типов), slog_gen (генератор кода), slog_rt (готовые подпрограммы).
Подробности языка: docs/SLOG.md
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from slog_gen import Gen          # noqa: E402
from slog_lex import SlogError    # noqa: E402
from slog_link import load        # noqa: E402


def compile_source(src, base_dir=None, lib_dirs=None):
    return Gen(load(src, base_dir, lib_dirs)).generate()


def main():
    if len(sys.argv) != 3:
        sys.exit("использование: slog.py программа.sl программа.pta")
    try:
        out = compile_source(open(sys.argv[1], encoding="utf-8").read(),
                             os.path.dirname(os.path.abspath(sys.argv[1])))
    except SlogError as e:
        sys.exit(f"ошибка: {e}")
    open(sys.argv[2], "w", encoding="utf-8").write(out)
    print(f"ok: {sys.argv[2]}")


if __name__ == "__main__":
    main()