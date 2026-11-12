#include <stdint.h>
#include "../vm/vm.h"
#include "ptfs.h"

#define UART_BASE 0x10000000u
#define UART_THR (*(volatile uint8_t *)(UART_BASE + 0)) /* запись: передать байт */
#define UART_RBR (*(volatile uint8_t *)(UART_BASE + 0)) /* чтение: принятый байт */
#define UART_LSR (*(volatile uint8_t *)(UART_BASE + 5)) /* бит 0: есть байт, бит 5: можно слать */
#define EXIT (*(volatile uint32_t *)0x100000)
#define MTIME_LO (*(volatile uint32_t *)0x0200BFF8)
#define MTIME_HI (*(volatile uint32_t *)0x0200BFFC)
#define CMP_LO (*(volatile uint32_t *)0x02004000)
#define CMP_HI (*(volatile uint32_t *)0x02004004)

#ifndef TICK
#define TICK 1000000u /* 10 МГц * 0.1 с */
#endif

#define csr_read(r) ({ uint32_t v; asm volatile("csrr %0, " #r : "=r"(v)); v; })
#define csr_write(r, v) asm volatile("csrw " #r ", %0" ::"r"(v))
#define csr_set(r, v) asm volatile("csrs " #r ", %0" ::"r"(v))

extern void trap_entry(void);
static volatile uint32_t ticks;

/* ---------- вывод и ввод ---------- */
static void putc_(char c) { while (!(UART_LSR & 0x20)) {} UART_THR = c; }
static void puts_(const char *s) { while (*s) putc_(*s++); }

static void puthex(uint32_t v) {
    for (int i = 28; i >= 0; i -= 4) putc_("0123456789abcdef"[(v >> i) & 15]);
}

/* Печать десятичного числа без деления (ядро пока без расширения M) */
static void putdec(uint32_t v) {
    static const uint32_t p[10] = {1000000000u, 100000000u, 10000000u, 1000000u, 100000u,
                                   10000u, 1000u, 100u, 10u, 1u};
    int started = 0;
    for (int i = 0; i < 10; i++) {
        char d = '0';
        while (v >= p[i]) { v -= p[i]; d++; }
        if (d != '0' || started || i == 9) { putc_(d); started = 1; }
    }
}

static char getc_(void) {
    while (!(UART_LSR & 1)) asm volatile("wfi");
    return UART_RBR;
}

/* Читает строку с эхом и поддержкой Backspace */
static void readline(char *buf, int max) {
    int n = 0;
    for (;;) {
        char c = getc_();
        if (c == '\r' || c == '\n') { puts_("\r\n"); buf[n] = 0; return; }
        if ((c == 0x7f || c == 8) && n > 0) { n--; puts_("\b \b"); }
        else if (c >= 32 && c < 127 && n < max - 1) { buf[n++] = c; putc_(c); }
    }
}

/* ---------- время и ловушки ---------- */
static uint64_t mtime(void) {
    uint32_t hi, lo;
    do { hi = MTIME_HI; lo = MTIME_LO; } while (hi != MTIME_HI);
    return ((uint64_t)hi << 32) | lo;
}

static void set_timer(uint64_t t) {
    CMP_HI = 0xFFFFFFFFu;
    CMP_LO = (uint32_t)t;
    CMP_HI = (uint32_t)(t >> 32);
}

void trap_handler(void) {
    uint32_t cause = csr_read(mcause);
    if (cause & 0x80000000u) {
        if ((cause & 0xFFF) == 7) { ticks++; set_timer(mtime() + TICK); }
    } else if (cause == 11) {
        puts_("ecall caught\n");
        csr_write(mepc, csr_read(mepc) + 4);
    } else {
        puts_("unhandled trap, mcause=0x");
        puthex(cause);
        puts_(" mepc=0x");
        puthex(csr_read(mepc));
        puts_("\n");
        for (;;) {}
    }
}

/* ---------- носитель (дискета B) и файловая система ---------- */
#ifndef MEDIA_BASE
#define MEDIA_BASE 0x80400000u   /* пока "дискета" лежит в ОЗУ; потом тут будет драйвер флоппи */
#endif

void media_read(uint32_t lba, uint8_t *dst) {
    const uint8_t *src = (const uint8_t *)(MEDIA_BASE + lba * 512u);
    for (int i = 0; i < 512; i++) dst[i] = src[i];
}

static uint8_t prog[4096];
static int fs_ready;

static int fs_mount(void) {
    if (fs_ready) return 1;
    int r = ptfs_mount();
    if (r != PTFS_OK) {
        puts_("no disk B, error ");
        putdec((uint32_t)(-r));
        puts_("\n");
        return 0;
    }
    fs_ready = 1;
    return 1;
}

/* ---------- виртуальная машина ---------- */
static vm_t vm;
static uint8_t vm_mem[2048];

/* Системные вызовы байткода: 1 = putc, 2 = getc (без ожидания, -1 если нет символа) */
static int kernel_sys(vm_t *v, uint8_t n, void *user) {
    (void)user;
    int32_t x;
    int r;
    switch (n) {
    case 1:
        if ((r = vm_pop(v, &x)) != 0) return r;
        putc_((char)x);
        return 0;
    case 2:
        return vm_push(v, (UART_LSR & 1) ? (int32_t)UART_RBR : -1);
    default:
        return VM_ERR_SYS;
    }
}

static void run_program(const uint8_t *img, uint32_t len) {
    int r = vm_load(&vm, img, len, vm_mem, sizeof vm_mem);
    if (r == 0) {
        vm.sys = kernel_sys;
        vm.user = 0;
        r = vm_run(&vm, 1000000);
    }
    if (r != VM_HALT) {
        puts_("vm error ");
        putdec((uint32_t)(-r));
        puts_("\n");
    }
}

/* ---------- шелл ---------- */
static int streq(const char *a, const char *b) {
    while (*a && *a == *b) { a++; b++; }
    return *a == *b;
}

static int starts(const char *s, const char *p) {
    while (*p) if (*s++ != *p++) return 0;
    return 1;
}

static int parse_hex(const char *s, uint32_t *out) {
    uint32_t v = 0;
    int n = 0;
    for (;; s++) {
        char c = *s;
        int d;
        if (c >= '0' && c <= '9') d = c - '0';
        else if (c >= 'a' && c <= 'f') d = c - 'a' + 10;
        else if (c >= 'A' && c <= 'F') d = c - 'A' + 10;
        else break;
        v = (v << 4) | d;
        n++;
    }
    *out = v;
    return n > 0 && *s == 0;
}

static void cmd_ls(void) {
    ptfs_entry e;
    if (!fs_mount()) return;
    for (int i = 0; ptfs_get(i, &e) == PTFS_OK; i++) {
        int n = 0;
        while (e.name[n]) n++;
        puts_(e.name);
        for (; n < 16; n++) putc_(' ');
        putdec(e.size);
        puts_(e.type == PTFS_T_BYTECODE ? " bytes  program\n" :
              e.type == PTFS_T_TEXT ? " bytes  text\n" : " bytes  data\n");
    }
}

static int load_file(const char *name, uint8_t want, ptfs_entry *e) {
    if (!fs_mount()) return 0;
    if (ptfs_find(name, e) != PTFS_OK) { puts_("no such file\n"); return 0; }
    if (e->type != want) { puts_(want == PTFS_T_TEXT ? "not a text file\n" : "not a program\n"); return 0; }
    int r = ptfs_read(e, prog, sizeof prog);
    if (r != PTFS_OK) {
        puts_("read error ");
        putdec((uint32_t)(-r));
        puts_("\n");
        return 0;
    }
    return 1;
}

static void cmd_cat(const char *name) {
    ptfs_entry e;
    if (!load_file(name, PTFS_T_TEXT, &e)) return;
    for (uint32_t i = 0; i < e.size; i++) putc_((char)prog[i]);
}

static void cmd_run(const char *name) {
    ptfs_entry e;
    if (!load_file(name, PTFS_T_BYTECODE, &e)) return;
    run_program(prog, e.size);
}

static void run(const char *l) {
    uint32_t a;
    if (*l == 0) return;
    if (streq(l, "help")) {
        puts_("help  - list commands\nver   - show version\necho  - print text\n");
        puts_("uptime - time since start\npeek  - read memory word (hex addr)\n");
        puts_("ls    - list files on disk B\ncat   - show text file (cat readme.txt)\n");
        puts_("run   - run program (run hello.ptb)\nexit  - stop emulator\n");
    } else if (streq(l, "ver")) {
        puts_("PT kernel 0.3 (RV32)\n");
    } else if (starts(l, "echo ")) {
        puts_(l + 5);
        puts_("\n");
    } else if (streq(l, "uptime")) {
        puts_("uptime: ");
        putdec(ticks);
        puts_(" ticks\n");
    } else if (starts(l, "peek ") && parse_hex(l + 5, &a)) {
        a &= ~3u;
        puthex(a);
        puts_(": ");
        puthex(*(volatile uint32_t *)a);
        puts_("\n");
    } else if (streq(l, "ls")) {
        cmd_ls();
    } else if (starts(l, "cat ")) {
        cmd_cat(l + 4);
    } else if (starts(l, "run ")) {
        cmd_run(l + 4);
    } else if (streq(l, "exit")) {
        EXIT = 0x5555;
    } else {
        puts_("unknown command, try: help\n");
    }
}

void main(void) {
    puts_("kernel: alive\n");
    csr_write(mtvec, (uint32_t)trap_entry);
    asm volatile("ecall");
    set_timer(mtime() + TICK);
    csr_set(mie, 0x80);
    csr_set(mstatus, 0x8);

    puts_("PT shell. type help\n");
    char line[64];
    for (;;) {
        puts_("> ");
        readline(line, sizeof line);
        run(line);
    }
}