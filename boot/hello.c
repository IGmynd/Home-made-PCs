#define UART (*(volatile unsigned char *)0x10000000)
#define EXIT (*(volatile unsigned int *)0x100000)

static void puts_(const char *s) { while (*s) UART = *s++; }

void main(void) {
    puts_("PT boot: hello from RV32IMC\n");
    EXIT = 0x5555;   /* команда QEMU завершить работу */
}