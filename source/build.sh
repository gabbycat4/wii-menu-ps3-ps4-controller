#!/bin/bash
# Builds ps3menu.c into ps3menu.bin and the Priiloader section ps3_ps4_controller.ini.
# Needs clang, ld.lld and llvm-objcopy (LLVM 15+), and python3.
set -e
cd "$(dirname "$0")"
clang --target=powerpc-unknown-eabi -mcpu=750 -Os -ffreestanding -fno-builtin -nostdlib -fno-pic -Wall $CFLAGS -c ps3menu.c -o ps3menu.o
ld.lld -T ps3menu.ld ps3menu.o -o ps3menu.elf
llvm-objcopy -O binary ps3menu.elf ps3menu.bin
echo "ps3menu.bin: $(stat -c%s ps3menu.bin) bytes (limit 6144)"
python3 make_ini.py
