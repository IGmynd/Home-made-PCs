"""Слог: сборка программы из модулей. Подставляет «подключить» и выбрасывает неиспользуемые функции библиотек."""
import os

from slog_lex import SlogError, register_file, tokenize
from slog_parse import Parser
from slog_types import stmt_exprs, walk

DEFAULT_LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")


def find_module(name, base_dir, lib_dirs):
    """Путь к файлу модуля или None. Ищем «имя» и «имя.sl» сначала в библиотеках, потом рядом
    с подключающим файлом. Так файл рядом с программой не может незаметно подменить библиотеку."""
    for d in list(lib_dirs) + [base_dir]:
        if d is None:
            continue
        for cand in (name, name + ".sl"):
            p = os.path.join(d, cand)
            if os.path.isfile(p):
                return os.path.normpath(p)
    return None


def load(src, base_dir=None, lib_dirs=None):
    """Разбирает главную программу и все подключённые модули, возвращает общий список команд.

    Функции главного файла остаются всегда, функции подключённых модулей остаются только
    если до них можно дойти вызовами."""
    lib_dirs = [DEFAULT_LIB] if lib_dirs is None else lib_dirs
    loop_ids = [0]
    seen = set()

    def parse(text, fid, here):
        prog = Parser(tokenize(text, fid), loop_ids).program()
        out = []
        for st in prog:
            if st[0] != "include":
                out.append(st)
                continue
            _, name, line = st
            path = find_module(name, here, lib_dirs)
            if path is None:
                raise SlogError(line, f"модуль «{name}» не найден (искали в библиотеке и рядом с программой)")
            if path in seen:
                continue
            seen.add(path)
            mfid = register_file(os.path.basename(path))
            with open(path, encoding="utf-8") as f:
                out += parse(f.read(), mfid, os.path.dirname(path))
        return out

    prog = parse(src, 0, base_dir)
    return shake(prog)


def calls_in(body, found):
    for st in body:
        for e in stmt_exprs(st):
            for x in walk(e):
                if x[0] == "call":
                    found.add(x[1])
        if st[0] == "if":
            for _, b in st[1]:
                calls_in(b, found)
            if st[2]:
                calls_in(st[2], found)
        elif st[0] == "while":
            calls_in(st[2], found)
        elif st[0] == "for":
            calls_in(st[3], found)


def shake(prog):
    """Оставляет функции главного файла и те функции библиотек, которые реально вызываются."""
    funcs = {}
    for st in prog:
        if st[0] == "func":
            if st[1] in funcs:
                raise SlogError(st[4], f"функция «{st[1]}» уже определена")
            funcs[st[1]] = st
    top = [st for st in prog if st[0] != "func"]
    keep = set()
    todo = []
    for name, st in funcs.items():
        if st[4] >> 20 == 0:                     # функция главного файла
            keep.add(name)
            todo.append(name)
    start = set()
    calls_in(top, start)
    for name in start:
        if name in funcs and name not in keep:
            keep.add(name)
            todo.append(name)
    while todo:
        found = set()
        calls_in(funcs[todo.pop()][3], found)
        for name in found:
            if name in funcs and name not in keep:
                keep.add(name)
                todo.append(name)
    return [st for st in prog if st[0] != "func" or st[1] in keep]