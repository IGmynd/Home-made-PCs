"""Слог: разборщик. Строит из слов дерево программы."""
from slog_lex import SlogError

PRINT = "печать"
RANGE = "диапазон"
CMPOPS = {"==", "!=", "<", "<=", ">", ">="}
AUGOPS = {"+=": "+", "-=": "-", "*=": "*", "//=": "//", "%=": "%"}


class Parser:
    def __init__(self, toks):
        self.t, self.p = toks, 0
        self.fid = 0               # номера циклов «для», чтобы скрытые переменные не пересекались

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
        if k == "KW" and v == "для":
            return self.for_stmt()
        if k == "KW" and v in ("иначе", "иначе_если"):
            raise SlogError(line, f"«{v}» без соответствующего «если»")
        st = self.simple()
        self.expect("NEWLINE", what="конец строки")
        return st

    def for_stmt(self):
        line = self.next()[2]
        var = self.expect("NAME", what="имя переменной цикла")[1]
        self.expect("NAME", "в", what="«в»")      # «в» особое слово только в заголовке «для»
        nxt = self.t[self.p + 1]
        if self.at("NAME", RANGE) and nxt[0] == "OP" and nxt[1] == "(":
            self.next()
            self.next()
            args = [self.p_or()]
            while self.accept("OP", ","):
                args.append(self.p_or())
            self.expect("OP", ")")
            if len(args) > 3:
                raise SlogError(line, "«диапазон» принимает от 1 до 3 аргументов")
            spec = ("range", args)
        else:
            spec = ("iter", self.expr())
        self.expect("OP", ":")
        self.fid += 1
        fid = self.fid
        return ("for", var, spec, self.block(), line, fid)

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
        if k == "NAME" and v == PRINT:
            nxt = self.t[self.p + 1]
            if nxt[0] == "OP" and nxt[1] == "(":
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
        e = self.expr()
        if self.at("OP", "="):
            self.next()
            rhs = self.expr()
            if e[0] == "var":
                return ("assign", e[1], rhs, line)
            if e[0] == "index":
                return ("setindex", e[1], e[2], rhs, line)
            raise SlogError(line, "слева от «=» должно стоять имя или элемент списка")
        if self.peek()[0] == "OP" and self.peek()[1] in AUGOPS:
            op = AUGOPS[self.next()[1]]
            rhs = self.expr()
            if e[0] == "var":
                return ("aug", e[1], op, rhs, line)
            if e[0] == "index":
                return ("augindex", e[1], e[2], op, rhs, line)
            raise SlogError(line, "слева от составного присваивания должно стоять имя или элемент списка")
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
        return self.p_postfix()

    def p_postfix(self):
        e = self.p_primary()
        while self.at("OP", "["):
            line = self.next()[2]
            idx = self.p_or()
            self.expect("OP", "]")
            e = ("index", e, idx, line)
        return e

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
        if k == "OP" and v == "[":
            elems = []
            if not self.at("OP", "]"):
                while True:
                    elems.append(self.p_or())
                    if not self.accept("OP", ","):
                        break
            self.expect("OP", "]")
            return ("list", elems, line)
        got = "конец файла" if k == "EOF" else "конец строки" if k == "NEWLINE" else repr(v)
        raise SlogError(line, f"ожидалось выражение, а найдено {got}")