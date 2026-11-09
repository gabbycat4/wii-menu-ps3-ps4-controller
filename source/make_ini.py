import struct
NAME = "PS3/PS4 Controller"
BASE, LIMIT = 0x80001800, 0x80003000
SITES = [0x81334D88, 0x81335284, 0x813354D0, 0x813356EC]  # getControllerManager()->read() in System::run / backup_run / reset_run / warning_run
b = open('ps3menu.bin', 'rb').read()
assert BASE + len(b) <= LIMIT and len(b) % 4 == 0
words = struct.unpack('>%dI' % (len(b) // 4), b)
lines = []; n = 0
for i in range(0, len(words), 64):   # 64 words per line (Priiloader's own list has lines of ~550)
    lines.append("offset=0x%08x" % (BASE + i * 4))
    lines.append("patch=" + ",".join("0x%08x" % w for w in words[i:i+64])); n += 1
for s in SITES:
    d = BASE - s
    assert -0x2000000 <= d < 0x2000000, "branch out of range"
    lines.append("offset=0x%08x" % s)
    lines.append("patch=0x%08x" % (0x48000001 | (d & 0x03FFFFFC))); n += 1
out = ["[%s]" % NAME, "minversion=513", "maxversion=513", "amount=%d" % n] + lines
open('ps3_ps4_controller.ini', 'w', newline='\n').write("\n".join(out) + "\n")
print(n, "patches,", len(b), "bytes")
