"""Слог: лексер. Превращает текст программы в список слов с учётом отступов."""

KEYWORDS = {"если", "иначе_если", "иначе", "пока", "для", "функция", "вернуть", "прервать",
            "продолжить", "пропуск", "глобальная", "и", "или", "не", "истина", "ложь"}

# цифры шестнадцатеричных чисел: 0-9 и русские А Б В Г Д Е (10-15), регистр любой
HEX_DIGITS = {**{str(d): d for d in range(10)},
              "А": 10, "Б": 11, "В": 12, "Г": 13, "Д": 14, "Е": 15,
              "а": 10, "б": 11, "в": 12, "г": 13, "д": 14, "е": 15}


class SlogError(Exception):
    def __init__(self, line, msg):
        super().__init__(f"строка {line}: {msg}")


def is_cyr(ch):
    return "\u0400" <= ch <= "\u04ff" and ch.isalpha()


def lex_number(s, i, lineno):
    """Число с позиции i. Десятичное, 0ш... (шестнадцатеричное), 0д... (двоичное). Возвращает (значение, конец)."""
    n = len(s)
    if s[i] == "0" and i + 1 < n and s[i + 1] in "шШдД":
        hexa = s[i + 1] in "шШ"
        j = i + 2
        v = 0
        while j < n and (s[j] in HEX_DIGITS if hexa else s[j] in "01"):
            v = v * (16 if hexa else 2) + (HEX_DIGITS[s[j]] if hexa else int(s[j]))
            j += 1
        if j == i + 2:
            if j < n and s[j].isalnum():
                raise SlogError(lineno, "недопустимая цифра в числе (в 0д только 0 и 1, в 0ш цифры 0-9 и А-Е)")
            raise SlogError(lineno, "после 0ш или 0д должны идти цифры")
        if j < n and (is_cyr(s[j]) or s[j] == "_" or s[j].isalnum()):
            raise SlogError(lineno, "недопустимая цифра в числе (в 0д только 0 и 1, в 0ш цифры 0-9 и А-Е)")
        if v > 0xFFFFFFFF:
            raise SlogError(lineno, "число не помещается в 32 бита")
        if v >= 0x80000000:
            v -= 1 << 32            # 0шЕЕЕЕЕЕЕЕ это -1
        return v, j
    j = i
    while j < n and "0" <= s[j] <= "9":
        j += 1
    if j < n and (is_cyr(s[j]) or s[j] == "_" or s[j].isalpha()):
        raise SlogError(lineno, "после числа не может идти буква")
    v = int(s[i:j])
    if v > 2147483647:
        raise SlogError(lineno, f"число {v} слишком велико (максимум 2147483647)")
    return v, j


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
            v, i = lex_number(s, i, lineno)
            toks.append(("NUM", v, lineno))
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
            elif ch in "+-*%()[]&|^~<>=,:":
                op = ch
            else:
                raise SlogError(lineno, f"недопустимый символ {ch!r}")
            if op in ("(", "["):
                depth += 1
            elif op in (")", "]"):
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