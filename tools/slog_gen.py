"""Слог: генератор. Обходит дерево программы и выдаёт ассемблер байткода ПТ."""
from slog_lex import KEYWORDS, SlogError
from slog_parse import PRINT, RANGE

# встроенные функции-выражения: имя -> число аргументов
BUILTINS = {"символ": 1, "ввод_символ": 0, "читать": 1, "писать": 2,
            "читать_байт": 1, "писать_байт": 2, "выделить": 1,
            "список": 1, "длина": 1}
RESERVED = KEYWORDS | set(BUILTINS) | {PRINT, RANGE}

BINOPS = {"+": "add", "-": "sub", "*": "mul", "//": "div", "%": "mod", "&": "and", "|": "or",
          "^": "xor", "<<": "shl", ">>": "sar", "==": "eq", "!=": "ne", "<": "lt", "<=": "le",
          ">": "gt", ">=": "ge"}

TRAP_INDEX = 1      # индекс вне списка
TRAP_SIZE = 2       # недопустимый размер списка


def const_int(e):
    """Значение выражения, если это число-константа (в том числе с унарным минусом), иначе None."""
    if e[0] == "num":
        return e[1]
    if e[0] == "un" and e[1] == "-" and e[2][0] == "num":
        return -e[2][1]
    return None


class Gen:
    def __init__(self, prog):
        self.prog = prog
        self.funcs = {}        # имя -> (метка, параметры, строка)
        self.globals = {}      # имя -> метка
        self.strings = []      # (метка, байты)
        self.code = []
        self.n = 0
        self.fn = None         # контекст функции: dict(locals)
        self.loops = []        # (метка продолжения, метка выхода)
        self.used_pnum = self.used_pstr = self.used_idx = self.used_new = False

    def new(self, prefix):
        self.n += 1
        return f"{prefix}{self.n}"

    def emit(self, op, arg=None):
        self.code.append(f"        {op}" + (f" {arg}" if arg is not None else ""))

    def label(self, name):
        self.code.append(f"{name}:")

    # --- предварительный проход: какие переменные где живут
    def children(self, st):
        """Вложенные блоки команды."""
        if st[0] == "if":
            return [b for _, b in st[1]] + ([st[2]] if st[2] else [])
        if st[0] == "while":
            return [st[2]]
        if st[0] == "for":
            return [st[3]]
        return []

    def assigned(self, body, out):
        for st in body:
            if st[0] == "assign":
                out.setdefault(st[1], st[3])
            elif st[0] == "aug":
                out.setdefault(st[1], st[4])
            elif st[0] == "for":
                _, var, spec, _, line, fid = st
                out.setdefault(var, line)
                hidden = (f"@сч{fid}", f"@кон{fid}") if spec[0] == "range" else (f"@спис{fid}", f"@инд{fid}")
                for h in hidden:
                    out.setdefault(h, line)
            for b in self.children(st):
                self.assigned(b, out)

    def declared_globals(self, body, out):
        for st in body:
            if st[0] == "global":
                for nm in st[1]:
                    out.setdefault(nm, st[2])
            for b in self.children(st):
                self.declared_globals(b, out)

    def reject_global_stmt(self, body):
        for st in body:
            if st[0] == "global":
                raise SlogError(st[2], "«глобальная» допустима только внутри функции")
            for b in self.children(st):
                self.reject_global_stmt(b)

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
        self.reject_global_stmt(top)
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
        elif k == "list":
            elems = e[1]
            self.emit("push", len(elems))
            self.emit("call", "__new")
            self.used_new = True
            for i, el in enumerate(elems):
                self.emit("dup")                  # ( адрес адрес )
                self.emit("push", 4 + 4 * i)
                self.emit("add")                  # ( адрес адрес_элемента )
                self.expr(el)                     # ( адрес адрес_элемента значение )
                self.emit("swap")
                self.emit("st32")                 # ( адрес )
        elif k == "index":
            self.index_addr(e)
            self.emit("ld32")
        elif k == "call":
            self.call(e)
        else:
            raise SlogError(0, f"внутренняя ошибка: {k}")

    def index_addr(self, e):
        """Кладёт на стек адрес элемента списка, проверив границы."""
        self.expr(e[1])
        self.expr(e[2])
        self.emit("call", "__idx")
        self.used_idx = True

    def call(self, e):
        _, name, args, line = e
        if name == PRINT:
            raise SlogError(line, "«печать» это команда, её нельзя использовать внутри выражения")
        if name == RANGE:
            raise SlogError(line, "«диапазон» можно использовать только в цикле «для»")
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
            elif name == "выделить":
                self.emit("alloc")
            elif name == "список":
                self.emit("call", "__new")
                self.used_new = True
            elif name == "длина":
                self.emit("ld32")
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
        elif k == "setindex":                       # а[и] = знач
            self.expr(st[3])
            self.index_addr(("index", st[1], st[2], st[4]))
            self.emit("st32")
        elif k == "augindex":                       # а[и] += знач
            self.index_addr(("index", st[1], st[2], st[5]))
            self.emit("dup")
            self.emit("ld32")
            self.expr(st[4])
            self.emit(BINOPS[st[3]])
            self.emit("swap")
            self.emit("st32")
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
                raise SlogError(st[1], "«прервать» допустимо только внутри цикла")
            self.emit("jmp", self.loops[-1][1])
        elif k == "continue":
            if not self.loops:
                raise SlogError(st[1], "«продолжить» допустимо только внутри цикла")
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
        elif k == "for":
            self.for_stmt(st)
        elif k == "func":
            raise SlogError(st[4], "функции определяются только на верхнем уровне")
        else:
            raise SlogError(0, f"внутренняя ошибка: {k}")

    def for_stmt(self, st):
        _, var, spec, body, line, fid = st
        top, cont, end = self.new("L_for"), self.new("L_fcont"), self.new("L_fend")
        if spec[0] == "range":
            args = spec[1]
            step = 1
            if len(args) == 3:
                step = const_int(args[2])
                if step is None:
                    raise SlogError(line, "шаг в «диапазон» должен быть числом-константой")
                if step == 0:
                    raise SlogError(line, "шаг в «диапазон» не может быть нулём")
            start = args[0] if len(args) >= 2 else ("num", 0, line)
            stop = args[1] if len(args) >= 2 else args[0]
            cnt, lim = f"@сч{fid}", f"@кон{fid}"
            self.expr(start)
            self.store(cnt, line)
            self.expr(stop)
            self.store(lim, line)
            self.label(top)
            self.load(cnt, line)
            self.load(lim, line)
            self.emit("lt" if step > 0 else "gt")
            self.emit("jz", end)
            self.load(cnt, line)
            self.store(var, line)
            self.loops.append((cont, end))
            self.body(body)
            self.loops.pop()
            self.label(cont)
            self.load(cnt, line)
            self.emit("push", step)
            self.emit("add")
            self.store(cnt, line)
            self.emit("jmp", top)
            self.label(end)
        else:                                        # по элементам списка
            lst, idx = f"@спис{fid}", f"@инд{fid}"
            self.expr(spec[1])
            self.store(lst, line)
            self.emit("push", 0)
            self.store(idx, line)
            self.label(top)
            self.load(idx, line)
            self.load(lst, line)
            self.emit("ld32")
            self.emit("lt")
            self.emit("jz", end)
            self.load(lst, line)                     # элемент: список + 4 + 4 * индекс
            self.load(idx, line)
            self.emit("push", 4)
            self.emit("mul")
            self.emit("add")
            self.emit("push", 4)
            self.emit("add")
            self.emit("ld32")
            self.store(var, line)
            self.loops.append((cont, end))
            self.body(body)
            self.loops.pop()
            self.label(cont)
            self.load(idx, line)
            self.emit("push", 1)
            self.emit("add")
            self.store(idx, line)
            self.emit("jmp", top)
            self.label(end)

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
        if self.used_new:
            self.code += [
                "; создать список из n слов ( n -- адрес ); в первом слове хранится длина",
                "__new:",
                "        dup", "        push 0", "        lt", "        jnz __new_bad",
                "        dup", "        push 16777216", "        gt", "        jnz __new_bad",
                "        dup", "        push 1", "        add", "        push 4", "        mul",
                "        alloc", "        swap", "        over", "        st32", "        ret",
                "__new_bad:", f"        trap {TRAP_SIZE}"]
        if self.used_idx:
            self.code += [
                "; адрес элемента списка с проверкой границ ( список индекс -- адрес )",
                "__idx:",
                "        over", "        ld32", "        over", "        gt", "        jz __idx_bad",
                "        dup", "        push 0", "        lt", "        jnz __idx_bad",
                "        push 4", "        mul", "        add", "        push 4", "        add", "        ret",
                "__idx_bad:", f"        trap {TRAP_INDEX}"]

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
        return "\n".join(["; сгенерировано slog.py, руками не править"] + data + [".code"] + self.code) + "\n"