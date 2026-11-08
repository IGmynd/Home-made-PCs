#include <stdint.h>

#define UART_BASE 0x10000000u
#define UART_THR (*(volatile uint8_t *)(UART_BASE + 0)) /* запись: передать байт */
#define UART_RBR (*(volatile uint8_t *)(UART_BASE + 0)) /* чтение: принятый байт */
#define UART_LSR (*(volatile uint8_t *)(UART_BASE + 5)) /* бит 0: есть принятый байт */
#define EXIT (*(volatile uint32_t *)0x100000)
#define MTIME_LO (*(volatile uint32_t *)0x0200BFF8)
#define MTIME_HI (*(volatile uint32_t *)0x0200BFFC)
#define CMP_LO (*(volatile uint32_t *)0x02004000)
#define CMP_HI (*(volatile uint32_t *)0x02004004)
#define TICK 1000000u /* 10 МГц * 0.1 с */

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

static void putdec(uint32_t v) {
    char b[10];
    int n = 0;
    do { b[n++] = '0' + v % 10; v /= 10; } while (v);
    while (n) putc_(b[--n]);
}

static char getc_(void) {
    while (!(UART_LSR & 1)) asm volatile("wfi"); /* спим до прерывания таймера */
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

static void run(const char *l) {
    uint32_t a;
    if (*l == 0) return;
    if (streq(l, "help")) {
        puts_("help  - list commands\nver   - show version\necho  - print text\n");
        puts_("uptime - time since start\npeek  - read memory word (hex addr)\nexit  - stop emulator\n");
    } else if (streq(l, "ver")) {
        puts_("PT kernel 0.1 (RV32IMC)\n");
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