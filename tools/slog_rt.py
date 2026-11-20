"""Слог: библиотека времени выполнения. Готовые подпрограммы на ассемблере ПТ.

Строка и список устроены одинаково: блок слов [длина][элемент 0][элемент 1]...
У строки элементы это коды символов Юникода.
"""

TRAP_INDEX = 1      # индекс вне списка
TRAP_SIZE = 2       # недопустимый размер списка

RT = {}             # имя -> (нужные подпрограммы, текст)


def define(name, deps, text):
    RT[name] = (deps, text.strip("\n"))


def runtime(used):
    """Строки ассемблера для всех нужных подпрограмм (с зависимостями)."""
    todo, seen = list(used), set()
    while todo:
        n = todo.pop()
        if n in seen:
            continue
        seen.add(n)
        todo.extend(RT[n][0])
    out = []
    for n in sorted(seen):
        out += RT[n][1].split("\n")
    return out


define("pnum", [], """
; вывод числа со знаком ( n -- )
__pnum:
        dup
        push 0
        lt
        jz __pnum_pos
        push 45
        sys 1
        neg
__pnum_pos:
        call __pdig
        ret
__pdig:
        dup
        push 10
        lt
        jnz __pdig_small
        dup
        push 10
        div
        call __pdig
        push 10
        mod
__pdig_small:
        push 48
        add
        sys 1
        ret
""")

define("putcp", [], """
; вывод одного символа Юникода в UTF-8 ( код -- )
__putcp:
        dup
        push 128
        lt
        jz __putcp_2
        sys 1
        ret
__putcp_2:
        dup
        push 2048
        lt
        jz __putcp_3
        dup
        push 6
        sar
        push 192
        or
        sys 1
        push 63
        and
        push 128
        or
        sys 1
        ret
__putcp_3:
        dup
        push 65536
        lt
        jz __putcp_4
        dup
        push 12
        sar
        push 224
        or
        sys 1
        dup
        push 6
        sar
        push 63
        and
        push 128
        or
        sys 1
        push 63
        and
        push 128
        or
        sys 1
        ret
__putcp_4:
        dup
        push 18
        sar
        push 240
        or
        sys 1
        dup
        push 12
        sar
        push 63
        and
        push 128
        or
        sys 1
        dup
        push 6
        sar
        push 63
        and
        push 128
        or
        sys 1
        push 63
        and
        push 128
        or
        sys 1
        ret
""")

define("pstrs", ["putcp"], """
; вывод строки ( строка -- )
__pstrs:
        frame 3
        stl 0
        ldl 0
        ld32
        stl 1
        push 0
        stl 2
__pstrs_loop:
        ldl 2
        ldl 1
        lt
        jz __pstrs_end
        ldl 0
        ldl 2
        push 4
        mul
        add
        push 4
        add
        ld32
        call __putcp
        ldl 2
        push 1
        add
        stl 2
        jmp __pstrs_loop
__pstrs_end:
        leave
        ret
""")

define("new", [], f"""
; создать список из n слов ( n -- адрес ); в первом слове хранится длина
__new:
        dup
        push 0
        lt
        jnz __new_bad
        dup
        push 16777216
        gt
        jnz __new_bad
        dup
        push 1
        add
        push 4
        mul
        alloc
        swap
        over
        st32
        ret
__new_bad:
        trap {TRAP_SIZE}
""")

define("idx", [], f"""
; адрес элемента списка с проверкой границ ( список индекс -- адрес )
__idx:
        over
        ld32
        over
        gt
        jz __idx_bad
        dup
        push 0
        lt
        jnz __idx_bad
        push 4
        mul
        add
        push 4
        add
        ret
__idx_bad:
        trap {TRAP_INDEX}
""")

define("scat", ["new"], """
; склеить две строки ( a b -- новая )
__scat:
        frame 6
        stl 1
        stl 0
        ldl 0
        ld32
        stl 2
        ldl 1
        ld32
        stl 3
        ldl 2
        ldl 3
        add
        call __new
        stl 4
        push 0
        stl 5
__scat_a:
        ldl 5
        ldl 2
        lt
        jz __scat_b0
        ldl 0
        ldl 5
        push 4
        mul
        add
        push 4
        add
        ld32
        ldl 4
        ldl 5
        push 4
        mul
        add
        push 4
        add
        st32
        ldl 5
        push 1
        add
        stl 5
        jmp __scat_a
__scat_b0:
        push 0
        stl 5
__scat_b:
        ldl 5
        ldl 3
        lt
        jz __scat_end
        ldl 1
        ldl 5
        push 4
        mul
        add
        push 4
        add
        ld32
        ldl 4
        ldl 5
        ldl 2
        add
        push 4
        mul
        add
        push 4
        add
        st32
        ldl 5
        push 1
        add
        stl 5
        jmp __scat_b
__scat_end:
        ldl 4
        leave
        ret
""")

define("seq", [], """
; равны ли две строки ( a b -- 0 или 1 )
__seq:
        frame 4
        stl 1
        stl 0
        ldl 0
        ld32
        stl 2
        ldl 1
        ld32
        ldl 2
        ne
        jz __seq_len_ok
        push 0
        leave
        ret
__seq_len_ok:
        push 0
        stl 3
__seq_loop:
        ldl 3
        ldl 2
        lt
        jz __seq_yes
        ldl 0
        ldl 3
        push 4
        mul
        add
        push 4
        add
        ld32
        ldl 1
        ldl 3
        push 4
        mul
        add
        push 4
        add
        ld32
        ne
        jz __seq_next
        push 0
        leave
        ret
__seq_next:
        ldl 3
        push 1
        add
        stl 3
        jmp __seq_loop
__seq_yes:
        push 1
        leave
        ret
""")

define("itos", ["new"], """
; число в строку ( n -- строка )
__itos:
        frame 6
        stl 0
        push 0
        stl 1
        ldl 0
        push 0
        lt
        jz __itos_pos
        push 1
        stl 1
        ldl 0
        neg
        stl 0
__itos_pos:
        ldl 0
        stl 3
        push 1
        stl 2
__itos_cnt:
        ldl 3
        push 10
        lt
        jnz __itos_alloc
        ldl 3
        push 10
        div
        stl 3
        ldl 2
        push 1
        add
        stl 2
        jmp __itos_cnt
__itos_alloc:
        ldl 2
        ldl 1
        add
        call __new
        stl 4
        ldl 2
        ldl 1
        add
        stl 5
__itos_fill:
        ldl 5
        push 1
        sub
        stl 5
        ldl 0
        push 10
        mod
        push 48
        add
        ldl 4
        ldl 5
        push 4
        mul
        add
        push 4
        add
        st32
        ldl 0
        push 10
        div
        stl 0
        ldl 5
        ldl 1
        gt
        jnz __itos_fill
        ldl 1
        jz __itos_done
        push 45
        ldl 4
        push 4
        add
        st32
__itos_done:
        ldl 4
        leave
        ret
""")

define("stoi", [], """
; строка в число ( строка -- n ); читает необязательный минус и цифры, остальное игнорирует
__stoi:
        frame 6
        stl 0
        ldl 0
        ld32
        stl 1
        push 0
        stl 2
        push 0
        stl 3
        push 0
        stl 4
        ldl 1
        push 0
        gt
        jz __stoi_done
        ldl 0
        push 4
        add
        ld32
        push 45
        eq
        jz __stoi_loop
        push 1
        stl 3
        push 1
        stl 2
__stoi_loop:
        ldl 2
        ldl 1
        lt
        jz __stoi_done
        ldl 0
        ldl 2
        push 4
        mul
        add
        push 4
        add
        ld32
        stl 5
        ldl 5
        push 48
        lt
        jnz __stoi_done
        ldl 5
        push 57
        gt
        jnz __stoi_done
        ldl 4
        push 10
        mul
        ldl 5
        push 48
        sub
        add
        stl 4
        ldl 2
        push 1
        add
        stl 2
        jmp __stoi_loop
__stoi_done:
        ldl 3
        jz __stoi_pos
        ldl 4
        neg
        leave
        ret
__stoi_pos:
        ldl 4
        leave
        ret
""")

define("chr", ["new"], """
; строка из одного символа ( код -- строка )
__chr:
        push 1
        call __new
        swap
        over
        push 4
        add
        st32
        ret
""")

define("slice", ["new"], """
; срез строки ( строка от до -- новая ), границы подрезаются, до не включается
__slice:
        frame 7
        stl 2
        stl 1
        stl 0
        ldl 0
        ld32
        stl 3
        ldl 1
        push 0
        lt
        jz __sl_a1
        push 0
        stl 1
__sl_a1:
        ldl 1
        ldl 3
        gt
        jz __sl_b0
        ldl 3
        stl 1
__sl_b0:
        ldl 2
        push 0
        lt
        jz __sl_b1
        push 0
        stl 2
__sl_b1:
        ldl 2
        ldl 3
        gt
        jz __sl_n
        ldl 3
        stl 2
__sl_n:
        ldl 2
        ldl 1
        sub
        stl 6
        ldl 6
        push 0
        lt
        jz __sl_alloc
        push 0
        stl 6
__sl_alloc:
        ldl 6
        call __new
        stl 4
        push 0
        stl 5
__sl_loop:
        ldl 5
        ldl 6
        lt
        jz __sl_end
        ldl 0
        ldl 1
        ldl 5
        add
        push 4
        mul
        add
        push 4
        add
        ld32
        ldl 4
        ldl 5
        push 4
        mul
        add
        push 4
        add
        st32
        ldl 5
        push 1
        add
        stl 5
        jmp __sl_loop
__sl_end:
        ldl 4
        leave
        ret
""")
define("scmp", [], """
; сравнение строк по кодам символов ( a b -- -1, 0 или 1 )
__scmp:
        frame 6
        stl 1
        stl 0
        ldl 0
        ld32
        ldl 1
        ld32
        lt
        jz __scmp_b
        ldl 0
        ld32
        stl 3
        jmp __scmp_go
__scmp_b:
        ldl 1
        ld32
        stl 3
__scmp_go:
        push 0
        stl 2
__scmp_loop:
        ldl 2
        ldl 3
        lt
        jz __scmp_len
        ldl 0
        ldl 2
        push 4
        mul
        add
        push 4
        add
        ld32
        stl 4
        ldl 1
        ldl 2
        push 4
        mul
        add
        push 4
        add
        ld32
        stl 5
        ldl 4
        ldl 5
        lt
        jz __scmp_ge
        push -1
        leave
        ret
__scmp_ge:
        ldl 4
        ldl 5
        gt
        jz __scmp_next
        push 1
        leave
        ret
__scmp_next:
        ldl 2
        push 1
        add
        stl 2
        jmp __scmp_loop
__scmp_len:
        ldl 0
        ld32
        ldl 1
        ld32
        lt
        jz __scmp_len2
        push -1
        leave
        ret
__scmp_len2:
        ldl 0
        ld32
        ldl 1
        ld32
        gt
        jz __scmp_eq
        push 1
        leave
        ret
__scmp_eq:
        push 0
        leave
        ret
""")