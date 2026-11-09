ENTRY(ps3hook)
IOS_Open        = 0x81572B10;
IOS_OpenAsync   = 0x815729F8;
IOS_CloseAsync  = 0x81572C30;
IOS_Close       = 0x81572CF0;
IOS_Ioctl       = 0x815734A8;
IOS_IoctlAsync  = 0x81573370;
DCFlushRange    = 0x8152D934;
DCInvalidateRange = 0x8152D908;
IOS_Ioctlv      = 0x815737F8;
IOS_IoctlvAsync = 0x81573714;
MgrRead         = 0x81337500;
RevoRead        = 0x813360CC;
SECTIONS {
  .patch 0x80001800 : {
    KEEP(*(.text.ps3hook))
    *(.text .text.*)
    *(.rodata .rodata.* .sdata2 .sdata2.*)
    . = ALIGN(32);
    KEEP(*(.usbdata))
    . = ALIGN(32);
    KEEP(*(.state))
    *(.data .data.* .sdata .sdata.* .sbss .sbss.* .bss .bss.* COMMON)
    . = ALIGN(4);
  }
  ASSERT(. <= 0x80003000, "too big for 0x80001800-0x80003000")
  /DISCARD/ : { *(.comment) *(.note*) *(.llvm_addrsig) }
}
