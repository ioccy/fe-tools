#include "bus.h"
#include "defs.h"
#include "psd.h"
#include "hw.h"

xdata volatile REG_8XX PSD _at_ CSIOP;

bit psd_flash_success(uint16_t address)
{
    uint8_t s1, s2;
    
    while(1) {

        s1 = bus_read(address);
        s2 = bus_read(address);

        if (!((s1 ^ s2) & 0x40)) return 1;  // DQ6 stopped toggling

        if (s2 & 0x20)  // DQ5 set while DQ6 toggles
        {
            s1 = bus_read(address);
            s2 = bus_read(address);

            // Reset flash
            bus_write((address & 0xF000) + 0x0555, 0xAA);
            bus_write((address & 0xF000) + 0x0AAA, 0x55);
            bus_write(address, 0xF0);

            return !((s1 ^ s2) & 0x40);
        }
    }
}

void psd_sdp_unlock_full(uint16_t address)
{
    address = address & 0xF000;
	
    bus_write(address + 0x0555, 0xAA);
    bus_write(address + 0x0AAA, 0x55);
    bus_write(address + 0x0555, 0x80);
    bus_write(address + 0x0555, 0xAA);
    bus_write(address + 0x0AAA, 0x55);
    bus_write(address + 0x0555, 0x20);
	
    while ((bus_read(address) ^ bus_read(address)) & 0x40);
}

// Write of payload must start within 120 us from calling this function
void psd_sdp_unlock_byte(uint16_t address)
{
    address = address & 0xF000;
	
    bus_write(address + 0x0555, 0xAA);
    bus_write(address + 0x0AAA, 0x55);
    bus_write(address + 0x0555, 0xA0);
    
    while ((bus_read(address) ^ bus_read(address)) & 0x40);
}

bit psd_erase_sector(uint16_t address)
{
    address = address & 0xF000;
    
    bus_write(address + 0x0555, 0xAA);
    bus_write(address + 0x0AAA, 0x55);
    bus_write(address + 0x0555, 0x80);
    bus_write(address + 0x0555, 0xAA);
    bus_write(address + 0x0AAA, 0x55);
    bus_write(address, 0x30);

    return psd_flash_success(address);
}

bit psd_clear_flash(uint16_t address)
{
    address = address & 0xF000;
    
    bus_write(address + 0x0555, 0xAA);
    bus_write(address + 0x0AAA, 0x55);
    bus_write(address + 0x0555, 0x80);
    bus_write(address + 0x0555, 0xAA);
    bus_write(address + 0x0AAA, 0x55);
    bus_write(address + 0x0555, 0x10);
    
    return psd_flash_success(address);
}

uint8_t psd_flash_id(uint16_t address)
{
    uint8_t id = 0;
    
    address = address & 0xF000;

    bus_write(address + 0x0555, 0xAA);
    bus_write(address + 0x0AAA, 0x55);
    bus_write(address + 0x0555, 0x90);

    id = bus_read((address & 0xFF80) + 0x01); // A6=0, A1=0, A0=1

    // Reset flash
    bus_write((address & 0xF000) + 0x0555, 0xAA);
    bus_write((address & 0xF000) + 0x0AAA, 0x55);
    bus_write(address, 0xF0);
    
    return id;
}

bit psd_write_flash(uint16_t address, uint8_t value)
{
    bus_write((address & 0xF000) + 0x0555, 0xAA);
    bus_write((address & 0xF000) + 0x0AAA, 0x55);
    bus_write((address & 0xF000) + 0x0555, 0xA0);
    bus_write(address, value);
    
    if (!psd_flash_success(address)) return 0;
    return bus_read(address) == value;
}

bit psd_write_eeprom(uint16_t address, uint8_t value)
{
    bus_write(address, value);
    delay_us(125);
    while ((bus_read(address) ^ bus_read(address)) & 0x40);
    return bus_read(address) == value;
}

uint8_t psd_read_rom(uint16_t addr)
{
    return bitbang_read(addr, SPACE_CODE);
}

bit psd_write_rom(uint16_t addr, uint8_t value)
{
    bitbang_write(addr, value, SPACE_CODE);
    delay_ms(1);
    while ((bitbang_read(addr, SPACE_CODE) ^ bitbang_read(addr, SPACE_CODE)) & 0x40);
    return bitbang_read(addr, SPACE_CODE) == value;
}
