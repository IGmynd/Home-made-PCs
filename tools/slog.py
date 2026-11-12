#!/usr/bin/env python3
"""Компилятор языка «Слог» в ассемблер байткода ПТ.

    slog.py программа.sl программа.pta

Язык похож на Питон, но все ключевые слова и имена по-русски (латиница в именах запрещена).
Подробности: docs/SLOG.md
"""
import sys

KEYWORDS = {"если", "иначе_если", "иначе", "пока", "функция", "вернуть", "прервать",
            "продолжить", "пропуск", "глобальная", "и", "или", "не", "истина", "ложь"}
PRINT = "печать"
# встроенные функции-выражения: имя -> число аргументов
BUILTINS = {"символ": 1, "ввод_символ": 0, "читать": 1, "писать": 2,
            "читать_байт": 1, "писать_байт": 2, "свободная_память": 0}
RESERVED = KEYWORDS | set(BUILTINS) | {PRINT}

BINOPS = {"+": "add", "-": "sub", "*": "mul", "//": "div", "%": "mod", "&": "and", "|": "or",
          "^": "xor", "<<": "shl", ">>": "sar", "==": "eq", "!=": "ne", "<": "lt", "<=": "le",
          ">": "gt", ">=": "ge"}
CMPOPS = {"==", "!=", "<", "<=", ">", ">="}
AUGOPS = {"+=": "+", "-=": "-", "*=": "*", "//=": "//", "%=": "%"}


class SlogError(Exception):
    def __init__(self, line, msg):
        super().__init__(f"строка {line}: {msg}")


# ---------------------------------------------------------------- лексер
def is_cyr(ch):
    return "\u0400" <= ch <= "\u04ff" and ch.isalpha()


def lex_line(s, lineno, toks, depth):
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if ch == " ":
            i += 1
        elif ch == "#":
            break
        elif ch == '"':
            i += 1
            buf = []
            while True:
                if i >= n:
                    raise SlogError(lineno, "строка не закрыта кавычкой")
                c = s[i]
                if c == '"':
                    i += 1
                    break
                if c == "\\":
                    i += 1
                    if i >= n:
                        raise SlogError(lineno, "обрыв после обратной косой черты")
                    e = s[i]
                    table = {"н": "\n", "т": "\t", '"': '"', "\\": "\\"}
                    if e not in table:
                        raise SlogError(lineno, f"неизвестная последовательность \\{e} (есть \\н \\т \\\" \\\\)")
                    buf.append(table[e])
                else:
                    buf.append(c)
                i += 1
            toks.append(("STR", "".join(buf), lineno))
        elif "0" <= ch <= "9":
            j = i
            while j < n and "0" <= s[j] <= "9":
                j += 1
            if j < n and (is_cyr(s[j]) or s[j] == "_" or s[j].isalpha()):
                raise SlogError(lineno, "после числа не может идти буква")
            v = int(s[i:j])
            if v > 2147483647:
                raise SlogError(lineno, f"число {v} слишком велико (максимум 2147483647)")
            toks.append(("NUM", v, lineno))
            i = j
        elif ch == "_" or is_cyr(ch):
            j = i
            while j < n and (s[j] == "_" or is_cyr(s[j]) or "0" <= s[j] <= "9"):
                j += 1
            if j < n and s[j].isalpha():
                raise SlogError(lineno, f"латинские и прочие буквы в именах не допускаются: {s[j]!r}")
            word = s[i:j]
            toks.append(("KW" if word in KEYWORDS else "NAME", word, lineno))
            i = j
        elif ch.isalpha():
            raise SlogError(lineno, f"латинские и прочие буквы в именах не допускаются: {ch!r}")
        else:
            three, two = s[i:i + 3], s[i:i + 2]
            if three == "//=":
                op = three
            elif two in ("//", "==", "!=", "<=", ">=", "<<", ">>", "+=", "-=", "*=", "%="):
                op = two
            elif ch in "+-*%()&|^~<>=,:":
                op = ch
            else:
                raise SlogError(lineno, f"недопустимый символ {ch!r}")
            if op == "(":
                depth += 1
            elif op == ")":
                depth -= 1
                if depth < 0:
                    raise SlogError(lineno, "лишняя закрывающая скобка")
            toks.append(("OP", op, lineno))
            i += len(op)
    return depth


def tokenize(src):
    toks, indents, depth = [], [0], 0
    lineno = 0
    for lineno, raw in enumerate(src.split("\n"), 1):
        line = raw.rstrip("\r")
        stripped = line.lstrip(" ")
        if depth == 0:
            if stripped.startswith("\t"):
                raise SlogError(lineno, "табуляция запрещена, отступы делаются пробелами")
            if stripped == "" or stripped.startswith("#"):
                continue
            ind = len(line) - len(stripped)
            if ind > indents[-1]:
                indents.append(ind)
                toks.append(("INDENT", None, lineno))
            else:
                while ind < indents[-1]:
                    indents.pop()
                    toks.append(("DEDENT", None, lineno))
                if ind != indents[-1]:
                    raise SlogError(lineno, "неровный отступ")
        depth = lex_line(stripped, lineno, toks, depth)
        if depth == 0:
            toks.append(("NEWLINE", None, lineno))
    if depth != 0:
        raise SlogError(lineno, "не закрыта скобка")
    while len(indents) > 1:
        indents.pop()
        toks.append(("DEDENT", None, lineno))
    toks.append(("EOF", None, lineno))
    return toks


# ---------------------------------------------------------------- разбор
class Parser:
    def __init__(self, toks):
        self.t, self.p = toks, 0

    def peek(self):
        return self.t[self.p]

    def next(self):
        tok = self.t[self.p]
        self.p += 1
        return tok

    def at(self, kind, val=None):
        k, v, _ = self.t[self.p]
        return k == kind and (val is None or v == val)

    def accept(self, kind, val=None):
        if self.at(kind, val):
            return self.next()
        return None

    def expect(self, kind, val=None, what=None):
        if self.at(kind, val):
            return self.next()
        k, v, line = self.peek()
        got = "конец файла" if k == "EOF" else "конец строки" if k == "NEWLINE" else repr(v) if v is not None else k
        raise SlogError(line, f"ожидалось {what or val or kind}, а найдено {got}")

    def program(self):
        body = []
        while not self.at("EOF"):
            body.append(self.statement(top=True))
        return body

    def block(self):
        """После ':'. Либо одна простая команда в той же строке, либо блок с отступом."""
        if not self.at("NEWLINE"):
            st = self.simple()
            self.expect("NEWLINE", what="конец строки")
            return [st]
        self.next()
        self.expect("INDENT", what="отступ (блок не может быть пустым, используйте «пропуск»)")
        body = []
        while not self.at("DEDENT"):
            if self.at("EOF"):
                break
            body.append(self.statement(top=False))
        self.accept("DEDENT")
        return body

    def statement(self, top):
        k, v, line = self.peek()
        if k == "KW" and v == "функция":
            if not top:
                raise SlogError(line, "функции определяются только на верхнем уровне")
            self.next()
            name = self.expect("NAME", what="имя функции")[1]
            self.expect("OP", "(")
            params = []
            if not self.at("OP", ")"):
                while True:
                    params.append(self.expect("NAME", what="имя параметра")[1])
                    if not self.accept("OP", ","):
                        break
            self.expect("OP", ")")
            self.expect("OP", ":")
            return ("func", name, params, self.block(), line)
        if k == "KW" and v == "если":
            self.next()
            arms = []
            cond = self.expr()
            self.expect("OP", ":")
            arms.append((cond, self.block()))
            els = None
            while self.at("KW", "иначе_если"):
                self.next()
                cond = self.expr()
                self.expect("OP", ":")
                arms.append((cond, self.block()))
            if self.accept("KW", "иначе"):
                self.expect("OP", ":")
                els = self.block()
            return ("if", arms, els, line)
        if k == "KW" and v == "пока":
            self.next()
            cond = self.expr()
            self.expect("OP", ":")
            return ("while", cond, self.block(), line)
        if k == "KW" and v in ("иначе", "иначе_если"):
            raise SlogError(line, f"«{v}» без соответствующего «если»")
        st = self.simple()
        self.expect("NEWLINE", what="конец строки")
        return st

    def simple(self):
        k, v, line = self.peek()
        if k == "KW":
            if v == "вернуть":
                self.next()
                e = None if self.at("NEWLINE") else self.expr()
                return ("return", e, line)
            if v in ("прервать", "продолжить", "пропуск"):
                self.next()
                return ({"прервать": "break", "продолжить": "continue", "пропуск": "pass"}[v], line)
            if v == "глобальная":
                self.next()
                names = [self.expect("NAME", what="имя")[1]]
                while self.accept("OP", ","):
                    names.append(self.expect("NAME", what="имя")[1])
                return ("global", names, line)
        if k == "NAME":
            nxt = self.t[self.p + 1]
            if v == PRINT and nxt[0] == "OP" and nxt[1] == "(":
                self.next()
                self.next()
                args = []
                if not self.at("OP", ")"):
                    while True:
                        args.append(self.expr())
                        if not self.accept("OP", ","):
                            break
                self.expect("OP", ")")
                return ("print", args, line)
            if nxt[0] == "OP" and nxt[1] == "=":
                self.next()
                self.next()
                return ("assign", v, self.expr(), line)
            if nxt[0] == "OP" and nxt[1] in AUGOPS:
                self.next()
                op = self.next()[1]
                return ("aug", v, AUGOPS[op], self.expr(), line)
        e = self.expr()
        return ("expr", e, line)

    # --- выражения
    def expr(self):
        return self.p_or()

    def p_or(self):
        l = self.p_and()
        while self.at("KW", "или"):
            line = self.next()[2]
            l = ("or", l, self.p_and(), line)
        return l

    def p_and(self):
        l = self.p_not()
        while self.at("KW", "и"):
            line = self.next()[2]
            l = ("and", l, self.p_not(), line)
        return l

    def p_not(self):
        if self.at("KW", "не"):
            line = self.next()[2]
            return ("not", self.p_not(), line)
        return self.p_cmp()

    def p_cmp(self):
        l = self.p_bor()
        k, v, line = self.peek()
        if k == "OP" and v in CMPOPS:
            self.next()
            r = self.p_bor()
            k2, v2, _ = self.peek()
            if k2 == "OP" and v2 in CMPOPS:
                raise SlogError(line, "цепочки сравнений не поддерживаются, используйте «и»")
            return ("bin", v, l, r, line)
        return l

    def _left(self, sub, ops):
        l = sub()
        while self.peek()[0] == "OP" and self.peek()[1] in ops:
            k, v, line = self.next()
            l = ("bin", v, l, sub(), line)
        return l

    def p_bor(self):
        return self._left(self.p_bxor, ("|",))

    def p_bxor(self):
        return self._left(self.p_band, ("^",))

    def p_band(self):
        return self._left(self.p_shift, ("&",))

    def p_shift(self):
        return self._left(self.p_add, ("<<", ">>"))

    def p_add(self):
        return self._left(self.p_mul, ("+", "-"))

    def p_mul(self):
        return self._left(self.p_unary, ("*", "//", "%"))

    def p_unary(self):
        k, v, line = self.peek()
        if k == "OP" and v in ("-", "~"):
            self.next()
            return ("un", v, self.p_unary(), line)
        return self.p_primary()

    def p_primary(self):
        k, v, line = self.next()
        if k == "NUM":
            return ("num", v, line)
        if k == "STR":
            return ("str", v, line)
        if k == "KW" and v in ("истина", "ложь"):
            return ("num", 1 if v == "истина" else 0, line)
        if k == "NAME":
            if self.at("OP", "("):
                self.next()
                args = []
                if not self.at("OP", ")"):
                    while True:
                        args.append(self.p_or())
                        if not self.accept("OP", ","):
                            break
                self.expect("OP", ")")
                return ("call", v, args, line)
            return ("var", v, line)
        if k == "OP" and v == "(":
            e = self.p_or()
            self.expect("OP", ")")
            return e
        got = "конец файла" if k == "EOF" else "конец строки" if k == "NEWLINE" else repr(v)
        raise SlogError(line, f"ожидалось выражение, а найдено {got}")


# ---------------------------------------------------------------- генерация
class Gen:
    def __init__(self, prog):
        self.prog = prog
        self.funcs = {}        # имя -> (метка, параметры, строка)
        self.globals = {}      # имя -> метка
        self.strings = []      # (метка, байты)
        self.code = []
        self.n = 0
        self.fn = None         # контекст функции: dict(locals, globals_decl)
        self.loops = []
        self.used_pnum = self.used_pstr = False

    def new(self, prefix):
        self.n += 1
        return f"{prefix}{self.n}"

    def emit(self, op, arg=None):
        self.code.append(f"        {op}" + (f" {arg}" if arg is not None else ""))

    def label(self, name):
        self.code.append(f"{name}:")

    # --- предварительный проход
    def assigned(self, body, out):
        for st in body:
            if st[0] == "assign":
                out.setdefault(st[1], st[3])
            elif st[0] == "aug":
                out.setdefault(st[1], st[4])
            elif st[0] == "if":
                for _, b in st[1]:
                    self.assigned(b, out)
                if st[2]:
                    self.assigned(st[2], out)
            elif st[0] == "while":
                self.assigned(st[2], out)

    def declared_globals(self, body, out):
        for st in body:
            if st[0] == "global":
                for nm in st[1]:
                    out.setdefault(nm, st[2])
            elif st[0] == "if":
                for _, b in st[1]:
                    self.declared_globals(b, out)
                if st[2]:
                    self.declared_globals(st[2], out)
            elif st[0] == "while":
                self.declared_globals(st[2], out)

    def check_name(self, name, line, what):
        if name in RESERVED:
            raise SlogError(line, f"имя «{name}» зарезервировано языком, его нельзя использовать как {what}")

    def prepare(self):
        top = [st for st in self.prog if st[0] != "func"]
        for st in self.prog:
            if st[0] == "func":
                _, name, params, body, line = st
                self.check_name(name, line, "имя функции")
                if name in self.funcs:
                    raise SlogError(line, f"функция «{name}» уже определена")
                if len(set(params)) != len(params):
                    raise SlogError(line, "повторяющиеся имена параметров")
                for p in params:
                    self.check_name(p, line, "имя параметра")
                self.funcs[name] = (f"f_{len(self.funcs)}", params, line)
        names = {}
        self.assigned(top, names)
        for st in top:
            self.reject_global_stmt(st)
        for st in self.prog:
            if st[0] == "func":
                g = {}
                self.declared_globals(st[3], g)
                for nm, ln in g.items():
                    names.setdefault(nm, ln)
        for name, ln in sorted(names.items(), key=lambda kv: kv[1]):
            self.check_name(name, ln, "имя переменной")
            if name in self.funcs:
                raise SlogError(ln, f"имя «{name}» занято функцией, переменной оно быть не может")
            self.globals[name] = f"g_{len(self.globals)}"

    def reject_global_stmt(self, st):
        if st[0] == "global":
            raise SlogError(st[2], "«глобальная» допустима только внутри функции")
        if st[0] == "if":
            for _, b in st[1]:
                for s in b:
                    self.reject_global_stmt(s)
            for s in (st[2] or []):
                self.reject_global_stmt(s)
        if st[0] == "while":
            for s in st[2]:
                self.reject_global_stmt(s)

    # --- переменные
    def load(self, name, line):
        if self.fn and name in self.fn["locals"]:
            self.emit("ldl", self.fn["locals"][name])
        elif name in self.globals:
            self.emit("push", self.globals[name])
            self.emit("ld32")
        elif name in self.funcs:
            raise SlogError(line, f"«{name}» это функция, а не переменная (нужны скобки для вызова)")
        else:
            raise SlogError(line, f"переменная «{name}» нигде не задана")

    def store(self, name, line):
        if self.fn and name in self.fn["locals"]:
            self.emit("stl", self.fn["locals"][name])
        elif name in self.globals:
            self.emit("push", self.globals[name])
            self.emit("st32")
        else:
            raise SlogError(line, f"нельзя присвоить «{name}»")

    # --- выражения
    def expr(self, e):
        k = e[0]
        if k == "num":
            self.emit("push", e[1])
        elif k == "str":
            raise SlogError(e[2], "строка допустима только внутри «печать»")
        elif k == "var":
            self.load(e[1], e[2])
        elif k == "un":
            self.expr(e[2])
            self.emit("neg" if e[1] == "-" else "not")
        elif k == "bin":
            self.expr(e[2])
            self.expr(e[3])
            self.emit(BINOPS[e[1]])
        elif k == "not":
            self.expr(e[1])
            self.emit("push", 0)
            self.emit("eq")
        elif k == "and":
            lf, le = self.new("L_and_f"), self.new("L_and_e")
            self.expr(e[1])
            self.emit("jz", lf)
            self.expr(e[2])
            self.emit("push", 0)
            self.emit("ne")
            self.emit("jmp", le)
            self.label(lf)
            self.emit("push", 0)
            self.label(le)
        elif k == "or":
            lt, le = self.new("L_or_t"), self.new("L_or_e")
            self.expr(e[1])
            self.emit("jnz", lt)
            self.expr(e[2])
            self.emit("push", 0)
            self.emit("ne")
            self.emit("jmp", le)
            self.label(lt)
            self.emit("push", 1)
            self.label(le)
        elif k == "call":
            self.call(e)
        else:
            raise SlogError(0, f"внутренняя ошибка: {k}")

    def call(self, e):
        _, name, args, line = e
        if name == PRINT:
            raise SlogError(line, "«печать» это команда, её нельзя использовать внутри выражения")
        if name in BUILTINS:
            if len(args) != BUILTINS[name]:
                raise SlogError(line, f"«{name}» принимает аргументов: {BUILTINS[name]}, передано: {len(args)}")
            for a in args:
                self.expr(a)
            if name == "символ":
                self.emit("sys", 1)
                self.emit("push", 0)
            elif name == "ввод_символ":
                self.emit("sys", 2)
            elif name == "читать":
                self.emit("ld32")
            elif name == "читать_байт":
                self.emit("ld8")
            elif name == "писать":
                self.emit("swap")
                self.emit("st32")
                self.emit("push", 0)
            elif name == "писать_байт":
                self.emit("swap")
                self.emit("st8")
                self.emit("push", 0)
            elif name == "свободная_память":
                self.emit("push", "__data_end")
            return
        if name not in self.funcs:
            raise SlogError(line, f"функция «{name}» не определена")
        label, params, _ = self.funcs[name]
        if len(args) != len(params):
            raise SlogError(line, f"«{name}» принимает аргументов: {len(params)}, передано: {len(args)}")
        for a in args:
            self.expr(a)
        self.emit("call", label)

    # --- команды
    def body(self, stmts):
        for st in stmts:
            self.stmt(st)

    def stmt(self, st):
        k = st[0]
        if k == "assign":
            self.expr(st[2])
            self.store(st[1], st[3])
        elif k == "aug":
            self.load(st[1], st[4])
            self.expr(st[3])
            self.emit(BINOPS[st[2]])
            self.store(st[1], st[4])
        elif k == "expr":
            self.expr(st[1])
            self.emit("drop")
        elif k == "print":
            args = st[1]
            for i, a in enumerate(args):
                if i:
                    self.emit("push", 32)
                    self.emit("sys", 1)
                if a[0] == "str":
                    label = f"s_{len(self.strings)}"
                    self.strings.append((label, a[1].encode("utf-8")))
                    self.emit("push", label)
                    self.emit("call", "__pstr")
                    self.used_pstr = True
                else:
                    self.expr(a)
                    self.emit("call", "__pnum")
                    self.used_pnum = True
            self.emit("push", 10)
            self.emit("sys", 1)
        elif k == "return":
            if not self.fn:
                raise SlogError(st[2], "«вернуть» допустимо только внутри функции")
            if st[1] is None:
                self.emit("push", 0)
            else:
                self.expr(st[1])
            self.emit("leave")
            self.emit("ret")
        elif k == "break":
            if not self.loops:
                raise SlogError(st[1], "«прервать» допустимо только внутри «пока»")
            self.emit("jmp", self.loops[-1][1])
        elif k == "continue":
            if not self.loops:
                raise SlogError(st[1], "«продолжить» допустимо только внутри «пока»")
            self.emit("jmp", self.loops[-1][0])
        elif k in ("pass", "global"):
            pass
        elif k == "if":
            end = self.new("L_if_end")
            for cond, body in st[1]:
                nxt = self.new("L_if_next")
                self.expr(cond)
                self.emit("jz", nxt)
                self.body(body)
                self.emit("jmp", end)
                self.label(nxt)
            if st[2]:
                self.body(st[2])
            self.label(end)
        elif k == "while":
            top, end = self.new("L_while"), self.new("L_wend")
            self.label(top)
            self.expr(st[1])
            self.emit("jz", end)
            self.loops.append((top, end))
            self.body(st[2])
            self.loops.pop()
            self.emit("jmp", top)
            self.label(end)
        elif k == "func":
            raise SlogError(st[4], "функции определяются только на верхнем уровне")
        else:
            raise SlogError(0, f"внутренняя ошибка: {k}")

    def function(self, st):
_, name, params, body, line = st
        label, _, _ = self.funcs[name]
        decl = {}
        self.declared_globals(body, decl)
        for p in params:
            if p in decl:
                raise SlogError(line, f"параметр «{p}» нельзя объявить глобальной переменной")
        locs = {p: i for i, p in enumerate(params)}
        found = {}
        self.assigned(body, found)
        for name2, ln in sorted(found.items(), key=lambda kv: kv[1]):
            if name2 in decl or name2 in params:
                continue
            self.check_name(name2, ln, "имя переменной")
            if name2 in self.funcs:
                raise SlogError(ln, f"имя «{name2}» занято функцией")
            locs[name2] = len(locs)
        if len(locs) > 255:
            raise SlogError(line, "слишком много локальных переменных (максимум 255)")
        self.fn = {"locals": locs}
        self.code.append(f"; функция {name}")
        self.label(label)
        self.emit("frame", len(locs))
        for i in reversed(range(len(params))):
            self.emit("stl", i)
        self.body(body)
        self.emit("push", 0)
        self.emit("leave")
        self.emit("ret")
        self.fn = None

    def runtime(self):
        if self.used_pstr:
            self.code += [
                "; вывод строки ( адрес -- )", "__pstr:", "__pstr_loop:",
                "        dup", "        ld8", "        dup", "        jz __pstr_end", "        sys 1",
                "        push 1", "        add", "        jmp __pstr_loop", "__pstr_end:",
                "        drop", "        drop", "        ret"]
        if self.used_pnum:
            self.code += [
                "; вывод числа со знаком ( n -- )", "__pnum:",
                "        dup", "        push 0", "        lt", "        jz __pnum_pos",
                "        push 45", "        sys 1", "        neg", "__pnum_pos:",
                "        call __pdig", "        ret",
                "__pdig:", "        dup", "        push 10", "        lt", "        jnz __pdig_small",
                "        dup", "        push 10", "        div", "        call __pdig",
                "        push 10", "        mod", "__pdig_small:",
                "        push 48", "        add", "        sys 1", "        ret"]

    def generate(self):
        self.prepare()
        main = [st for st in self.prog if st[0] != "func"]
        self.code.append("; --- основная программа")
        self.body(main)
        self.emit("halt")
        for st in self.prog:
            if st[0] == "func":
                self.function(st)
        self.runtime()
        data = [".data"]
        for name, label in self.globals.items():
            data.append(f"{label}: .word 0        ; {name}")
        for label, raw in self.strings:
            data.append(f"{label}: .byte " + ", ".join(str(b) for b in raw + b"\x00"))
        data.append("__data_end:")
        return "\n".join(["; сгенерировано slog.py, руками не править"] + data + [".code"] + self.code) + "\n"


def compile_source(src):
    prog = Parser(tokenize(src)).program()
    return Gen(prog).generate()


def main():
    if len(sys.argv) != 3:
        sys.exit("использование: slog.py программа.sl программа.pta")
    try:
        out = compile_source(open(sys.argv[1], encoding="utf-8").read())
    except SlogError as e:
        sys.exit(f"ошибка: {e}")
    open(sys.argv[2], "w", encoding="utf-8").write(out)
    print(f"ok: {sys.argv[2]}")


if __name__ == "__main__":
    main()
         