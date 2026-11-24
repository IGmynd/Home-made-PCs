/* Время ядра: арифметика вынесена отдельно, чтобы проверять её на ПК (kernel/test_timeutil.c). */
#ifndef PT_TIMEUTIL_H
#define PT_TIMEUTIL_H

#include <stdint.h>

/* Миллисекунды с запуска.
   ticks        сколько раз сработал таймер ядра;
   tick_ms      длина одного такта таймера в миллисекундах;
   units_per_ms сколько единиц счётчика времени в миллисекунде;
   now_lo       младшие 32 бита счётчика сейчас;
   last_lo      они же в момент последнего срабатывания таймера.
   Всё считается в 32 битах с переполнением, 64-битного деления не нужно. */
static inline uint32_t time_ms(uint32_t ticks, uint32_t tick_ms, uint32_t units_per_ms,
                               uint32_t now_lo, uint32_t last_lo) {
    return ticks * tick_ms + (uint32_t)(now_lo - last_lo) / units_per_ms;
}

#endif