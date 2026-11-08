ENTRY(_start)
SECTIONS {
  . = 0x80100000;
  .text : { *(.text.init) *(.text*) }
  .rodata : { *(.rodata*) }
  .data : { *(.data*) }
  .bss : { *(.bss*) *(COMMON) }
  . = ALIGN(16);
  . += 4096;
  _stack_top = .;
}