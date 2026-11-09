# PS3/PS4 Controller for the Wii Menu

Use a wired **PlayStation 3 controller (DualShock 3)** or **PlayStation 4 controller (DualShock 4)** on your Wii's System Menu. The left analog stick moves the pointer and the buttons click, so you can open your channels, emulators and homebrew without a Wii Remote.

It's a **Priiloader hack**: a patch that Priiloader applies to the Wii Menu each time it starts. Nothing is installed to the Wii's internal memory, and you can turn it off in Priiloader at any time.

Only need PS3 controller support? The original PS3-only version is at [gabbycat4/wii-menu-ps3-controller](https://github.com/gabbycat4/wii-menu-ps3-controller).

## Requirements

- **A softmodded Wii with [Priiloader](https://github.com/DacoTaco/priiloader) installed.**
- **Wii Menu 4.3U (USA) only.** The patch writes to fixed memory addresses in that exact menu version. It will **not** load on 4.3E, 4.3J, 4.3K or older menus. Check your version under Wii Settings (top-right corner).
- **An official Sony controller on a USB cable, plugged into a USB port on the back of the Wii** (not through a hub). The hack looks for Sony's USB IDs, so clone controllers that report different IDs won't be detected:

  | Controller | USB ID |
  | --- | --- |
  | DualShock 3 (PS3) | `054c:0268` |
  | DualShock 4, original (CUH-ZCT1) | `054c:05c4` |
  | DualShock 4, newer with light bar on the touchpad (CUH-ZCT2) | `054c:09cc` |

  The model number is on the sticker on the back of a PS4 controller.
- An SD card you use with your Wii, and a computer to edit it.

## Controls

| Controller | Wii Remote |
| --- | --- |
| Left stick | Pointer |
| Cross (X) | A |
| Circle | B |
| Square | 1 |
| Triangle | 2 |
| L1, Select (PS3) or Share (PS4) | − |
| R1 | + |
| Start (PS3), Options (PS4) or PS button | HOME |
| D-pad | D-pad |

- The disc slot glows for about a second when the controller starts working.
- A PS4 controller's light bar turns **red**.
- You can plug a controller in before turning the Wii on, or at the menu.
- If both a PS3 and a PS4 controller are plugged in when it looks for one, the PS3 one is used. Once a controller is working it stays in charge: plugging in a second one doesn't switch over. Unplug the one in use and the other takes over.
- A real Wii Remote keeps working alongside it.
- This works in the **Wii Menu only**. Once you start a game, channel or emulator, that program decides which controllers it supports.

## Install

All of the installers do the same thing: they add the `[PS3/PS4 Controller]` section to the end of `apps/priiloader/hacks_hash.ini` on your SD card. If you've installed it before, the old copy gets replaced, including the older `[PS3 Controller]` version. If the SD card has no hacks file yet, they start from Priiloader's standard list. They also save a backup of your original file as `hacks_hash.ini.before-ps3`.

First, download this repo: click the green **Code** button → **Download ZIP**, then unzip it. Plug your Wii's SD card into your computer.

### Windows

Double-click **`install.bat`**. It finds the SD card on its own and tells you what it did.

If it can't tell which drive is the SD card, open PowerShell in the folder and give it the drive letter:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 E:\
```

### Linux and macOS

Open a terminal in the unzipped folder and run:

```bash
bash install.sh
```

If it can't find the SD card, give it the card's folder:

```bash
bash install.sh /run/media/$USER/SDCARD    # Linux
bash install.sh /Volumes/SDCARD            # macOS
```

### By hand (any computer)

1. Open `apps/priiloader/hacks_hash.ini` on the SD card in a plain text editor (Notepad, TextEdit in plain-text mode, Kate, etc.).
2. If there's an older `[PS3 Controller]` or `[PS3/PS4 Controller]` section, delete it: everything from that line down to the line just before the next `[` section (or the end of the file).
3. Copy the entire contents of [`ps3_ps4_controller.ini`](ps3_ps4_controller.ini) and paste it at the **end** of the file.
4. **Make sure there are no blank lines anywhere in the file.** Priiloader stops reading at the first blank line, so any hacks after it won't show up.
5. Save the file.

### Turn it on

1. Safely eject the SD card and put it back in the Wii.
2. Start Priiloader (hold **Reset** while turning the Wii on).
3. Go to **System Menu Hacks**, turn on **PS3/PS4 Controller**, and choose **save settings**. Priiloader keeps its own copy of your hacks, so it won't use the new file until you save.
4. Plug in your controller and boot the System Menu.

**Switching from the PS3-only version:** the installers replace its "PS3 Controller" entry (the two use the same memory, so they can't both be on). Tick **PS3/PS4 Controller** in Priiloader after installing.

## Remove

Turn off **PS3/PS4 Controller** in Priiloader's System Menu Hacks. To take it out of the hacks file completely:

- Windows: `install.bat -Remove`
- Linux/macOS: `bash install.sh --remove`
- By hand: delete everything from the `[PS3/PS4 Controller]` line down to the line just before the next `[` section (or the end of the file).

## Files

| File | What it is |
| --- | --- |
| `ps3_ps4_controller.ini` | The hack itself, in Priiloader's hacks file format |
| `install.bat` / `install.ps1` | Windows installer |
| `install.sh` | Linux and macOS installer |
| `source/` | The hack's source code, build scripts and the simulator tests used to check each build (see `source/README.txt`) |
| `LICENSE` | The GNU General Public License, version 2 |

## Troubleshooting

- **"PS3/PS4 Controller" doesn't appear in Priiloader's hacks list.** Your menu probably isn't 4.3U, or there's a blank line earlier in `hacks_hash.ini`. Run the installer again, since it removes blank lines.
- **It still behaves like the old version.** Choose **save settings** in Priiloader's System Menu Hacks after updating the SD card.
- **A PS4 controller doesn't respond after you plug it in.** Press its **PS button**. A PS4 controller that was unplugged while it was on can need that to wake up.
- **The controller doesn't work after a fresh boot,** especially after some Virtual Console games. Something in the Wii can claim the controller before the menu starts. Unplug it and plug it back in at the menu.
- **The pointer doesn't move.** Use a USB cable plugged directly into the Wii (not a hub) and an official Sony controller.
- **Something went wrong.** Copy `hacks_hash.ini.before-ps3` back over `hacks_hash.ini` to undo everything, and please open an issue saying what happened.

## Credits

- The hack is loaded by [Priiloader](https://github.com/DacoTaco/priiloader) by DacoTaco and contributors. The installers include a copy of Priiloader's standard `hacks_hash.ini` list for use when your SD card doesn't have one.
- The way the controller appears to the menu as a Wii Remote follows the [Wii Menu GameCube controller hack](https://github.com/maxwelmota/wiimenu-gcn-hack-enhanced) by maxwelmota, after dg4l.
- Wii Menu 4.3U addresses come from the [wii-ipl](https://github.com/koopthekoopa/wii-ipl) decompilation.
- Made by [gabbycat4](https://github.com/gabbycat4).

## License

Copyright (C) 2026 gabbycat4

This project is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2 of the License or (at your option) any later version. See [`LICENSE`](LICENSE) for the full text.

It is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

Use at your own risk. This hack only changes what Priiloader loads into memory and doesn't write to the Wii's internal storage, but always keep a working backup of your NAND.
