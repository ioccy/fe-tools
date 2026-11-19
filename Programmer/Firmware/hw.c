#include <REG51F380.H>
#include "hw.h"

void init_emif(void)
{
    P1SKIP = 0xC8; // Exclude RD, WR, ALE from crossbar
    EMI0CF = 0x0F; // Mutiplexed mode, external memory, slowest ALE
    EMI0TC = 0xFF; // Set slowest timings
}

void init_ports(void)
{
    P0MDOUT |= 0x10; // Enable UTX as push-pull output
    XBR0     = 0x01; // Enable UART on P0.4(TX) and P0.5(RX)                     
    XBR1     = 0x40; // Enable crossbar and weak pull-ups
    
    // Park ports high (except ALE pin); digital mode; push-pull outputs
    P1 = 0xF7; P1MDIN = 0xFF; P1MDOUT = 0xFF;
    P3 = 0xFF; P3MDIN = 0xFF; P3MDOUT = 0xFF;
    P4 = 0xFF; P4MDIN = 0xFF; P4MDOUT = 0xFF;
}

void init_osc(void)
{
    OSCICN |= 0x03; // Switch to 12 MHz
    RSTSRC  = 0x04; // Enable missing clock detector
}

void init_uart(uint32_t baudrate)
{
   SCON0 = 0x10; // 8N0

   if (SYSCLK/baudrate/2/256 < 1) {
      TH1 = -(SYSCLK/baudrate/2);
      CKCON &= ~0x0B;                  // T1M = 1; SCA1:0 = xx
      CKCON |=  0x08;
   } else if (SYSCLK/baudrate/2/256 < 4) {
      TH1 = -(SYSCLK/baudrate/2/4);
      CKCON &= ~0x0B;                  // T1M = 0; SCA1:0 = 01                  
      CKCON |=  0x01;
   } else if (SYSCLK/baudrate/2/256 < 12) {
      TH1 = -(SYSCLK/baudrate/2/12);
      CKCON &= ~0x0B;                  // T1M = 0; SCA1:0 = 00
   } else {
      TH1 = -(SYSCLK/baudrate/2/48);
      CKCON &= ~0x0B;                  // T1M = 0; SCA1:0 = 10
      CKCON |=  0x02;
   }

   TL1 = TH1;                          // Init Timer1
   TMOD &= ~0xf0;                      // Timer 1 in 8-bit autoreload
   TMOD |=  0x20;                       
   TR1 = 1;                            // START Timer1
   TI0 = 1;                            // Indicate TX0 ready
}

void init_timer(void)
{
    TMOD &= ~0x0F;   // clear Timer0 mode bits
    TMOD |=  0x01;   // Timer0, Mode 1 (16-bit timer, C/T0 = 0)
    CKCON &= ~0x07;  // T0M = 0, SCA1:0 = 00  -> Timer0 clock = SYSCLK/12
    TR0 = 0;
    TF0 = 0;
}

// Blocking delay, 1 <= us <= 65535 (max ~65.5 ms per call at 12 MHz)
void delay_us(uint16_t us)
{
    uint16_t reload;

    if (us == 0) return;

    reload = (uint16_t)(65536UL - us);

    TR0 = 0;
    TH0 = (uint8_t)(reload >> 8);
    TL0 = (uint8_t)(reload & 0xFF);
    TF0 = 0;
    TR0 = 1;

    while (!TF0);

    TR0 = 0;
}

// Millisecond wrapper, chunks through delay_us to stay within the 16-bit range
void delay_ms(uint16_t ms)
{
    while (ms--) delay_us(1000);
}