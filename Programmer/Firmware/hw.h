#include "defs.h"

#ifndef HW_H
#define HW_H

#define SYSCLK 12000000 // Internal clock source

void init_emif(void);
void init_ports(void);
void init_osc(void);
void init_uart(unsigned long);
void init_timer(void);

// Blocking delay, 1 <= us <= 65535 (max ~65.5 ms per call at 12 MHz)
void delay_us(uint16_t us);

// Millisecond wrapper, chunks through delay_us to stay within the 16-bit range
void delay_ms(uint16_t ms);

#endif