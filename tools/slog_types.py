"""Слог: вывод типов. У каждого значения тип «int» (число, список, адрес) или «str» (строка).

Типы переменных, параметров и результатов функций определяются сами: компилятор
повторяет обход программы, пока что-то узнаёт. Если одна и та же переменная получает
и число, и строку, это ошибка.
"""
from slog_lex import SlogError

# встроенные функции, возвращающие строку (остальные возвращают число)
BUILTIN_RET = {"строка": "str", "из_кода": "str", "срез": "str", "строкой": "str"}


def line_of(e):
    k = e[0]
    if k in ("num", "str", "var", "not", "list"):
        return e[2]
    if k in ("call", "un", "and", "or", "index"):
        return e[3]
    if k == "bin":
        return e[4]
    return 0


def sub_exprs(e):
    """Прямые подвыражения."""
    k = e[0]
    if k == "un":
        return [e[2]]
    if k == "bin":
        return [e[2], e[3]]
    if k == "not":
        return [e[1]]
    if k in ("and", "or"):
        return [e[1], e[2]]
    if k == "list":
        return list(e[1])
    if k == "index":
        return [e[1], e[2]]
    if k == "call":
        return list(e[2])
    return []


def walk(e):
    yield e
    for s in sub_exprs(e):
        yield from walk(s)


def stmt_exprs(st):
    """Выражения команды (без вложенных блоков)."""
    k = st[0]
    if k == "assign":
        return [st[2]]
    if k == "aug":
        return [st[3]]
    if k == "setindex":
        return [st[1], st[2], st[3]]
    if k == "augindex":
        return [st[1], st[2], st[4]]
    if k == "expr":
        return [st[1]]
    if k == "print":
        return list(st[1])
    if k == "return":
        return [st[1]] if st[1] is not None else []
    if k == "if":
        return [c for c, _ in st[1]]
    if k == "while":
        return [st[1]]
    if k == "for":
        return list(st[2][1]) if st[2][0] == "range" else [st[2][1]]
    return []


class Types:
    def __init__(self, gen):
        self.gen = gen
        self.var = {}          # (область, имя) -> тип; область None это глобальные
        self.ret = {}          # имя функции -> тип результата
        self.changed = False

    def key(self, scope, name):
        if scope is not None and name in self.gen.func_info[scope]["locals"]:
            return (scope, name)
        return (None, name)

    def join(self, store, key, t, line, what):
        if t is None:
            return
        old = store.get(key)
        if old is None:
            store[key] = t
            self.changed = True
        elif old != t:
            raise SlogError(line, f"{what} получает и число, и строку (разные типы в одной переменной нельзя)")

    def of(self, e, scope):
        """Тип выражения или None, если пока не известен."""
        k = e[0]
        if k == "str":
            return "str"
        if k == "var":
            return self.var.get(self.key(scope, e[1]))
        if k == "bin":
            if e[1] == "+":
                tl, tr = self.of(e[2], scope), self.of(e[3], scope)
                if "str" in (tl, tr):
                    return "str"
                if tl is None or tr is None:
                    return None
            return "int"
        if k == "call":
            if e[1] in self.gen.funcs:
                return self.ret.get(e[1])
            return BUILTIN_RET.get(e[1], "int")
        return "int"

    def ty(self, e, scope):
        """Окончательный тип (незнакомое считаем числом)."""
        return self.of(e, scope) or "int"

    def block(self, scope, body):
        for st in body:
            k = st[0]
            if k == "assign":
                self.join(self.var, self.key(scope, st[1]), self.of(st[2], scope), st[3], f"переменная «{st[1]}»")
            elif k == "aug":
                t = self.of(("bin", st[2], ("var", st[1], st[4]), st[3], st[4]), scope)
                self.join(self.var, self.key(scope, st[1]), t, st[4], f"переменная «{st[1]}»")
            elif k == "for":
                self.join(self.var, self.key(scope, st[1]), "int", st[4], f"переменная цикла «{st[1]}»")
            elif k == "return" and scope is not None and st[1] is not None:
                self.join(self.ret, scope, self.of(st[1], scope), st[2], f"результат функции «{scope}»")
            for e in stmt_exprs(st):
                for x in walk(e):
                    if x[0] == "call" and x[1] in self.gen.funcs:
                        params = self.gen.funcs[x[1]][1]
                        if len(params) == len(x[2]):
                            for p, a in zip(params, x[2]):
                                self.join(self.var, (x[1], p), self.of(a, scope), x[3],
                                          f"параметр «{p}» функции «{x[1]}»")
            for b in self.gen.children(st):
                self.block(scope, b)

    def infer(self):
        for _ in range(60):
            self.changed = False
            self.block(None, self.gen.main_body)
            for name, info in self.gen.func_info.items():
                self.block(name, info["body"])
            if not self.changed:
                return