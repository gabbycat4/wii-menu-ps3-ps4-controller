PS3/PS4 Controller in the Wii Menu - Priiloader hack, source
==============================================================
For: Wii Menu 4.3U (v513), Priiloader 0.10, IOS80. Wired DualShock 3 (054C:0268)
and wired DualShock 4 (054C:09CC, 054C:05C4).

Files
  ps3menu.c           the hack (C). Comments at the top explain how it works.
  ps3menu.ld          linker script: Wii Menu function addresses (4.3U) and the
                      memory spot 0x80001800-0x80003000 (unused low memory).
  build.sh            compiles ps3menu.c and makes ps3_ps4_controller.ini.
  make_ini.py         turns ps3menu.bin into the Priiloader section, plus the
                      4 "bl ps3hook" patches at the controller-read calls:
                      0x81334D88 System::run, 0x81335284 backup_run,
                      0x813354D0 reset_run, 0x813356EC warning_run.
  ps3_ps4_controller.ini  the built Priiloader section, "PS3/PS4 Controller"
                      (build.sh writes it here; the released copy is in the folder above).
  (installers: install.sh / install.bat / install.ps1 in the folder above)
  sim/                a small PowerPC simulator and scenario tests used to check
                      each build before it went on the Wii:
                        ./build.sh && cd sim && python3 test_stage3.py && python3 test_ds4.py
                      (test_stage2.py is the older suite; its blink-code checks
                      fail on the final build, since the blinking is gone.)

Build notes
  - Built with clang (target powerpc-unknown-eabi, -mcpu=750 -Os). GCC/devkitPPC
    should also work but would give a different binary - re-run make_ini.py.
  - The binary must stay under 6144 bytes (the linker script checks this).
  - Function addresses come from the wii-ipl decompilation's 4.3U symbol list
    (github.com/koopthekoopa/wii-ipl, config/43U/symbols.txt). Other menu
    versions need different addresses.
  - After changing the SD file, choose "save settings" in Priiloader's
    System Menu Hacks, or the Wii keeps using the old copy.

How it works (short)
  - Each frame the menu reads its controllers; the 4 patched calls go to
    ps3hook instead, which calls the real read and then adds a fake Wii Remote
    (pointer from the left stick, buttons mapped below) in a free slot.
  - USB: /dev/usb/oh0/54c/268. Setup: SET_CONFIGURATION 1, feature reports
    F2/F5, F4 "enable" (42 0C 00 00), LED report. Then input report 0x01 reads.
  - Plug-in: an insertion hook (oh0 ioctlv 30, new devices only) is armed from
    the first frame; when it fires the device is opened straight from the IPC
    callback, beating the IOS service that otherwise grabs it.
  - Known limit: after some Arcade / Master System VC games the controller is
    grabbed before the menu starts. Unplug and replug it.

Controls
  Left stick pointer, Cross = A, Circle = B, Square = 1, Triangle = 2,
  L1/Select = -, R1 = +, Start/PS = HOME, D-pad = D-pad.

PS4 controller (stage 4)
  A wired DualShock 4 (054C:09CC CUH-ZCT2, or 054C:05C4 CUH-ZCT1) works the same
  way; if a PS3 controller is also plugged in, the PS3 one is used. Share = -,
  Options = HOME, the rest as above. The light bar is set to red. Each controller
  ID has its own plug-in hook, so PS4 controllers can be plugged in at the menu.
  How it reads the PS4 controller and what the Wii needed: see the comment at
  the top of ps3menu.c.
  Test build with blink codes:  CFLAGS=-DDIAG ./build.sh  (no light bar in it)
  Tests: ./build.sh && cd sim && python3 test_ds4.py && python3 test_stage3.py
         CFLAGS=-DDIAG ./build.sh && cd sim && python3 test_ds4.py diag
  make_ini.py writes 64 values per patch line (Priiloader's own list uses much
  longer lines), and names the section "PS3/PS4 Controller".

Recovery: hold Reset at power-on to open Priiloader and untick the hack.
