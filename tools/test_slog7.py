#!/usr/bin/env python3
"""Тесты «Слога»: время, пауза и библиотека случайных чисел sluchai.
Запуск: test_slog7.py путь/к/host"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptasm  # noqa: E402
import slog   # noqa: E402

HOST = sys.argv[1]
fails = 0


def run(src, stdin=b""):
    img = ptasm.assemble(slog.compile_source(src))
    with tempfile.NamedTemporaryFile(suffix=".ptb", delete=False) as f:
        f.write(img)
        path = f.name
    try:
        r = subprocess.run([HOST, path], input=stdin, capture_output=True, timeout=20)
    finally:
        os.unlink(path)
    return r.returncode, r.stdout.decode("utf-8"), r.stderr.decode("utf-8")


def ok(name, src, stdin, expected):
    global fails
    try:
        code, out, err = run(src, stdin)
    except Exception as e:  # noqa: BLE001
        fails += 1
        print(f"FAIL {name}: исключение {e}")
        return
    if code != 0 or out != expected:
        fails += 1
        print(f"FAIL {name}: код={code} вывод={out!r} ожидалось={expected!r} {err.strip()}")


def bad(name, src, fragment):
    global fails
    try:
        slog.compile_source(src)
    except slog.SlogError as e:
        if fragment not in str(e):
            fails += 1
            print(f"FAIL {name}: ошибка {e!s} не содержит {fragment!r}")
        return
    fails += 1
    print(f"FAIL {name}: ошибки не было, а ждали {fragment!r}")


def runtime_fail(name, src, fragment):
    global fails
    code, out, err = run(src)
    if code == 0 or fragment not in err:
        fails += 1
        print(f"FAIL {name}: код={code} stderr={err!r} ждали {fragment!r}")


# ---------- независимая реализация того же генератора (для сверки)
class Ref:
    def __init__(self, seed):
        self.s = seed & 0xFFFFFFFF

    def bits15(self):
        self.s = (self.s * 1103515245 + 12345) & 0xFFFFFFFF
        return (self.s >> 16) & 0x7FFF

    def below(self, n):
        if n <= 0 or n > 1073741824:
            return 0
        a = self.bits15()
        b = self.bits15()
        return ((a << 15) | b) % n


def draws(seed, n, count):
    r = Ref(seed)
    return [r.below(n) for _ in range(count)]


R = 'подключить "sluchai"\n'

# ================= время и пауза
ok("время не убывает", "а = время()\nб = время()\nпечать(б >= а)\n", b"", "1\n")
ok("время начинается около нуля", "печать(время() >= 0, время() < 3000)\n", b"", "1 1\n")
ok("пауза ждёт", "а = время()\nпауза(100)\nб = время()\nпечать(б - а >= 95, б - а < 1500)\n", b"", "1 1\n")
ok("две паузы складываются", "а = время()\nпауза(60)\nпауза(60)\nб = время()\nпечать(б - а >= 115)\n", b"", "1\n")
ok("пауза ноль и отрицательная не ждут", "а = время()\nпауза(0)\nпауза(-5)\nб = время()\nпечать(б - а < 50)\n", b"", "1\n")
ok("пауза возвращает ноль", "печать(пауза(5))\n", b"", "0\n")
bad("время с аргументом", "печать(время(1))\n", "принимает аргументов")
bad("пауза без аргумента", "пауза()\n", "принимает аргументов")
bad("пауза со строкой", 'пауза("а")\n', "ожидалось число")

# ================= случайные числа: точное совпадение с эталоном
def expected_line(vals):
    return " ".join(str(v) for v in vals) + "\n"


ok("сверка с эталоном, зерно 42", R + "посеять(42)\nдля к в диапазон(10):\n    печать(случайное(1000))\n",
   b"", "".join(f"{v}\n" for v in draws(42, 1000, 10)))
for seed in (0, 1, 12345, -1, 2147483647):
    lit = str(seed) if seed >= 0 else f"0 - {-seed}"
    ok(f"сверка с эталоном, зерно {seed}", R + f"посеять({lit})\nдля к в диапазон(6):\n    печать(случайное(100))\n",
       b"", "".join(f"{v}\n" for v in draws(seed, 100, 6)))
ok("сверка с эталоном, самое малое зерно", R + "посеять(0 - 2147483647 - 1)\nдля к в диапазон(5):\n    печать(случайное(50))\n",
   b"", "".join(f"{v}\n" for v in draws(-2147483648, 50, 5)))
ok("сверка с эталоном, большой диапазон", R + "посеять(9)\nдля к в диапазон(5):\n    печать(случайное(1073741824))\n",
   b"", "".join(f"{v}\n" for v in draws(9, 1073741824, 5)))
ok("сверка с эталоном, не степень двойки", R + "посеять(3)\nдля к в диапазон(8):\n    печать(случайное(7))\n",
   b"", "".join(f"{v}\n" for v in draws(3, 7, 8)))

# ================= свойства
ok("один и тот же посев даёт одно и то же", R + """
посеять(5)
а = [случайное(1000), случайное(1000), случайное(1000)]
посеять(5)
б = [случайное(1000), случайное(1000), случайное(1000)]
печать(а[0] == б[0] и а[1] == б[1] и а[2] == б[2])
""", b"", "1\n")
ok("разные посевы дают разное", R + """
посеять(5)
а = случайное(1000000)
посеять(6)
б = случайное(1000000)
печать(а != б)
""", b"", "1\n")
ok("случайное попадает в диапазон", R + """
посеять(11)
виден = список(6)
для к в диапазон(2000):
    виден[случайное(6)] = 1
итог = 0
для х в виден:
    итог += х
печать(итог)
""", b"", "6\n")
ok("случайное_от включает границы", R + """
посеять(13)
счёт = список(6)
для к в диапазон(600):
    счёт[случайное_от(1, 6) - 1] += 1
итог = 0
меньше_нуля = 0
для х в счёт:
    итог += х
    если х == 0:
        меньше_нуля += 1
печать(итог, меньше_нуля)
""", b"", "600 0\n")
ok("крайние запросы", R + "печать(случайное(0), случайное(-5), случайное(1), случайное(1073741825))\n", b"", "0 0 0 0\n")
ok("случайное_от с равными и перевёрнутыми границами", R + "печать(случайное_от(5, 5), случайное_от(7, 3))\n", b"", "5 7\n")
ok("посеять возвращает ноль", R + "печать(посеять(1))\n", b"", "0\n")
ok("точное распределение по корзинам", R + """
посеять(7)
счёт = список(10)
для к в диапазон(3000):
    счёт[случайное(10)] += 1
для х в счёт:
    печать(х)
""", b"", "".join(f"{sum(1 for v in draws(7, 10, 3000) if v == b)}\n" for b in range(10)))
ok("большой диапазон не выходит за границы", R + """
посеять(21)
плохих = 0
для к в диапазон(300):
    х = случайное(1073741824)
    если х < 0 или х >= 1073741824:
        плохих += 1
печать(плохих)
""", b"", "0\n")
ok("посев часами", R + "посеять(время())\nх = случайное(10)\nпечать(х >= 0 и х < 10)\n", b"", "1\n")

if fails == 0:
    print("SLOG7 TESTS PASS")
else:
    print(f"SLOG7 TESTS FAIL: {fails}")
sys.exit(1 if fails else 0)
