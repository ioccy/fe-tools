
#include <REG51F380.H>

#include "bus.h"
#include "hw.h"
#include "defs.h"

uint8_t EMIF_read(uint16_t address)
{
    return *((volatile uint8_t xdata *)address);
}

void EMIF_write(uint16_t address, uint8_t value)
{
    *((volatile uint8_t xdata *)address) = value;
}

uint8_t bitbang_read(uint16_t addr, bit space)
{
    uint8_t value;

    P3 = (uint8_t)(addr >> 8);

    P4MDOUT = 0xFF; // push-pull to drive the bus
    P4 = (uint8_t)(addr & 0xFF);

    P_ALE = 1;
    P_ALE = 0;

    P4MDOUT = 0x00; // open-drain to read
    P4 = 0xFF;      // tri-state / weak pull (so not to read back address if bus is not responding)

	if (space == SPACE_DATA) P_RD = 0; else P_PSEN = 0;
    if (P_PSEN) delay_us(1); else delay_us(10); // 10 us to read with /PSEN asserted
    value = P4;
    if (space == SPACE_DATA) P_RD = 1; else P_PSEN = 1;
    
    P4MDOUT = 0xFF; // back to push-pull for EMIF

    return value;
}

void bitbang_write(uint16_t addr, uint8_t value, bit space)
{
    P3 = (uint8_t)(addr >> 8);

    P4MDOUT = 0xFF; // push-pull to drive the bus
    P4 = (uint8_t)(addr & 0xFF);

    P_ALE = 1;
    P_ALE = 0;

    P4 = value;

    if (space == SPACE_CODE) P_PSEN = 0;
    P_WR = 0;
    if (P_PSEN) delay_us(1); else delay_us(10000); // 10 ms to write with /PSEN asserted
    P_WR = 1;
    if (space == SPACE_CODE) P_PSEN = 1;

    P4 = 0xFF; // tri-state / weak pull
}

/*
#ifdef BITBANG
uint8_t (*bus_read)(uint16_t) = bitbang_read;
void (*bus_write)(uint16_t, uint8_t) = bitbang_write;
#else
uint8_t (*bus_read)(uint16_t) = EMIF_read;
void (*bus_write)(uint16_t, uint8_t) = EMIF_write;
#endif
*/



uint8_t bus_read(uint16_t address)
{
    // return bitbang_read(address, SPACE_DATA);
    return EMIF_read(address);
}

void bus_write(uint16_t address, uint8_t value)
{
    // bitbang_write(address, value, SPACE_DATA);
    EMIF_write(address, value);
}
