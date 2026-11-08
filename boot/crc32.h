#include <stdint.h>

/* CRC32, совместим с zlib.crc32. Можно вызывать по кускам: crc = crc32_update(crc, buf, n), начиная с 0 */
static inline uint32_t crc32_update(uint32_t crc, const uint8_t *p, uint32_t n) {
    crc = ~crc;
    while (n--) {
        crc ^= *p++;
        for (int k = 0; k < 8; k++)
            crc = (crc >> 1) ^ (0xEDB88320u & -(crc & 1u));
    }
    return ~crc;
}