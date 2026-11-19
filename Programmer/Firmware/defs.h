#include <REG51F380.H>

#ifndef DEFS_H
#define DEFS_H

// Port wiring
// MCU P4 0:7 -> PSD AD 0:7
// MCU P3 0:7 -> PSD A 8:15

// Other pin assignments
sbit P_RESET = P1 ^ 0;
sbit P_PSEN  = P1 ^ 1;
sbit P_ALE   = P1 ^ 3; // Also used by EMIF
sbit P_RD    = P1 ^ 6; // Also used by EMIF
sbit P_WR    = P1 ^ 7; // Also used by EMIF

#define DEBUG

typedef unsigned char uint8_t;
typedef unsigned int  uint16_t;
typedef unsigned long uint32_t;

#endif