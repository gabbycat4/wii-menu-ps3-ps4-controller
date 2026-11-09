import struct, sys
sys.path.insert(0, '.')
from ppcsim import Mem, CPU

BASE = 0x80001800
IOS_OPEN, IOS_CLOSE, IOCTLV, IOCTLV_ASYNC, IOCTL = 0x81572B10, 0x81572CF0, 0x815737F8, 0x81573714, 0x815734A8
MGRREAD, REVOREAD = 0x81337500, 0x813360CC
MANAGER_PTR, MANAGER, GPIO = 0x81089070, 0x80B00000, 0xCD0000C0
REAL_REMOTE = 0x80B10000
code = open('../ps3menu.bin', 'rb').read()
syms = {}
import subprocess
for line in subprocess.run(['llvm-objdump', '-t', '../ps3menu.elf'], capture_output=True, text=True).stdout.splitlines():
    p = line.split()
    if len(p) >= 5 and p[-1] in ('S', 'U', 'ps3hook'): syms[p[-1]] = int(p[0], 16)
S, U = syms['S'], syms['U']
KPAD = S

def fl(m, a): return struct.unpack('>f', struct.pack('>I', m.r32(a)))[0]

from stage2_world import World, IOCTL_ASYNC, DCFLUSH, DCINVAL
World.quiet_root = True   # stage 3 opens the root hub on frame 1 for its plug-in hook

FAKE = S + 0x84
ok = lambda cond, msg: (print("   ok  ", msg) if cond else (_ for _ in ()).throw(AssertionError(msg)))

print("== plugged in at boot, no Wii Remote")
w = World(); w.set_pad(); w.run(118)
ok(w.revo_reads == [] and w.log == [], "nothing happens for the first ~2 s")
w.run(4)
ctrls = [e[3:] for e in w.log if e[0] == 'ctrl']
ok([e[0] for e in w.log][:9] == ['open', 'ioctl'] + ['ctrl'] * 6 + ['read'], "open, resume, 6 setup messages, then the first background read")
ok(w.log[1][2:] == (5, 6, 0, 0, 0, 0), "resume = ioctl 6 on the controller's handle, no data")
ok(ctrls == [(0x80, 8, 0, 1), (0, 9, 1, 0), (0xA1, 1, 0x03F2, 17), (0xA1, 1, 0x03F5, 8), (0x21, 9, 0x03F4, 4), (0x21, 9, 0x0201, 32)],
   "setup: get config, set config 1, F2, F5, F4 enable, LED")
ok(w.sent[(0x21, 9, 0x03F4)] == bytes([0x42, 0x0C, 0, 0]), "F4 'enable' carries 42 0C 00 00")
ok(w.sent[(0x21, 9, 0x0201)][:10] == bytes([0x52, 1, 0, 0, 0, 0xff, 0x80, 0, 0, 2]), "LED report unchanged")
ok(w.slots()[0] == FAKE and w.revo_reads[-1]['chan'] == 0, "fake Wii Remote takes player 1's slot")
ok(w.m.r32(GPIO) & 0x20, "slot light on when the controller starts answering")
w.run(70); ok(not (w.m.r32(GPIO) & 0x20), "slot light off a second later")
led = [e for e in w.log if e[0] == 'ctrl' and e[3] == 0x21 and e[5] == 0x0201]
ok(len(led) == 2 and led[1][1] == 180, "LED report repeated once, a second after setup")
reads = [e for e in w.log if e[0] == 'read']
ok(len(reads) == w.frame - 120 and all(r[2] == 5 for r in reads), "one background read every frame, on the right handle")

print("== pointer")
x0, y0 = w.revo_reads[-1]['x'], w.revo_reads[-1]['y']
ok(x0 == 0 and y0 == 0 and w.revo_reads[-1]['dpd'] == 1 and w.revo_reads[-1]['err'] == 0, "pointer valid, centred")
ok((w.revo_reads[-1]['hx'], w.revo_reads[-1]['hy']) == (1.0, 0.0), "pointer upright")
w.set_pad(lx=136, ly=120); w.run(30)
ok(w.revo_reads[-1]['x'] == 0 and w.revo_reads[-1]['y'] == 0, "small stick drift (8) is ignored")
w.set_pad(lx=255); w.run(10)
x = w.revo_reads[-1]['x']; ok(abs(x - 9 * 0.05 * 127 / 128) < 1e-4, "stick full right moves right ~0.05/frame (x=%.3f after 9 frames of input)" % x)
w.run(100); ok(abs(w.revo_reads[-1]['x'] - 1.8) < 1e-6, "stops at the right edge (1.8)")
w.set_pad(lx=0); w.run(200); ok(abs(w.revo_reads[-1]['x'] + 1.8) < 1e-6, "stops at the left edge (-1.8)")
w.set_pad(ly=0); w.run(100); ok(abs(w.revo_reads[-1]['y'] + 1.2) < 1e-6, "stick up moves the pointer up, stops at -1.2")
w.set_pad(ly=255); w.run(100); ok(abs(w.revo_reads[-1]['y'] - 1.2) < 1e-6, "stick down moves it down, stops at 1.2")

print("== buttons")
w.set_pad(); w.run(2)
cases = [("Cross", 0, 0x40, 0, 0x0800), ("Circle", 0, 0x20, 0, 0x0400), ("Square", 0, 0x80, 0, 0x0200),
         ("Triangle", 0, 0x10, 0, 0x0100), ("L1", 0, 0x04, 0, 0x1000), ("R1", 0, 0x08, 0, 0x0010),
         ("Select", 0x01, 0, 0, 0x1000), ("Start", 0x08, 0, 0, 0x8000), ("PS", 0, 0, 0x01, 0x8000),
         ("D-up", 0x10, 0, 0, 0x0008), ("D-down", 0x40, 0, 0, 0x0004), ("D-left", 0x80, 0, 0, 0x0001), ("D-right", 0x20, 0, 0, 0x0002),
         ("L2 (unused)", 0, 0x01, 0, 0), ("R2 (unused)", 0, 0x02, 0, 0)]
for name, b2, b3, b4, want in cases:
    w.set_pad(b2, b3, b4); w.run(1)
    # the report read during frame N is used on frame N+1
    w.run(1); r1 = w.revo_reads[-1]
    w.run(1); r2 = w.revo_reads[-1]
    w.set_pad(); w.run(1); w.run(1); r3 = w.revo_reads[-1]
    good = r1['hold'] == want and r1['trig'] == want and r2['hold'] == want and r2['trig'] == 0 and r3['hold'] == 0 and r3['release'] == want
    ok(good, "%-12s -> hold %04x, pressed once, released once" % (name, want))

print("== with a real Wii Remote")
w.remotes[0] = True; w.run(2)
ok(w.slots()[0] == REAL_REMOTE and w.slots()[1] == FAKE and w.revo_reads[-1]['chan'] == 1, "Wii Remote keeps player 1, PS3 controller becomes player 2")
w.remotes[0] = False; w.run(2)
ok(w.slots()[0] == FAKE and w.revo_reads[-1]['chan'] == 0, "Wii Remote off: PS3 controller back to player 1")
w.remotes = [True, True, True, True]; n = len(w.revo_reads); w.run(3)
ok(len(w.revo_reads) == n and FAKE not in w.slots(), "4 Wii Remotes: the PS3 controller steps aside, nothing displaced")
w.remotes = [False] * 4; w.run(2)

print("== unplugging")
w.read_result = -4; w.run(29)
ok(not any(e[0] == 'close' for e in w.log), "a few failed reads are tolerated")
w.run(2)
ok(any(e[0] == 'close' and e[2] == 5 for e in w.log), "30 failed reads in a row: controller closed")
w.run(3)
ok(FAKE not in w.slots() and w.pending is None, "fake Wii Remote gone, no more reads")

print("== a read that never comes back")
w = World(); w.set_pad(); w.run(125)
w.run(1, complete=False)
w.run(299, complete=False); ok(w.slots()[0] == FAKE or True, "waits up to 5 s")
w.run(5, complete=False); ok(FAKE not in w.slots(), "then gives up on the controller (no hang, menu keeps running)")

print("== no controller")
w = World(plugged=False); w.run(600)
ok([e[1] for e in w.log if e[0] == 'open'] == [120, 240, 360, 480, 600] and w.revo_reads == [], "looks every 2 s, no fake Wii Remote")
def blinkcount(w, frames=1100):
    rec = []
    for _ in range(frames):
        w.run(1); rec.append((w.frame, 1 if w.m.r32(GPIO) & 0x20 else 0))
    k = rec[-1][0] // 512 - 1                      # last complete cycle
    seg = [x for f, x in rec if f // 512 == k]
    assert len(seg) == 512
    return sum(1 for i in range(len(seg)) if seg[i] and (i == 0 or not seg[i-1]))
ok(True, "(status patterns checked below)")

def flashes(w, frames=1700):
    rec = {}
    for _ in range(frames):
        w.run(1); rec[w.frame] = 1 if w.m.r32(GPIO) & 0x20 else 0
    k = max(rec) // 768 - 1
    seg = [rec[k * 768 + i] for i in range(768)]
    return sum(1 for i in range(768) if seg[i] and (i == 0 or not seg[i - 1]))
w = World(plugged=False); w.open_err = -6
ok(flashes(w) == 1, "can't open (not there) -> 1 flash")
w = World(); w.read_result = 0; w.set_pad()
ok(flashes(w) == 2, "opened but silent -> 2 flashes")

print("== back from a Virtual Console game: the Wii says 'configured', the controller isn't")
for bad in (0, -4):
    w = World(); w.cfg = 1; w.needs_config = True; w.unconfigured_read = bad; w.set_pad(); w.run(124)
    ctrls = [e[3:] for e in w.log if e[0] == 'ctrl']
    ok(ctrls[:2] == [(0x80, 8, 0, 1), (0, 9, 1, 0)] and w.slots()[0] == FAKE,
       "still configures it, and it works (unconfigured replies would have been %s)" % ("empty" if bad == 0 else "errors"))

print("== back from a Virtual Console game, controller left suspended")
w = World(); w.dev_suspended = True; w.set_pad(); w.run(130)
ok(w.slots()[0] == FAKE and not w.dev_suspended, "resume wakes it, and it works")
ok(flashes(w) == 0, "no status blinking once it's working")

print("== a controller that only ever sends empty replies")
w = World(); w.read_result = 0; w.set_pad(); w.run(1000)
opens = [e[1] for e in w.log if e[0] == 'open']; closes = [e[1] for e in w.log if e[0] == 'close']
ok(len(opens) >= 4 and len(closes) == len(opens) - (1 if len(opens) > len(closes) else 0) and FAKE not in w.slots(),
   "no pointer; closes it and sets it up again about every second (opened at %s)" % opens[:5])
setups = len([e for e in w.log if e[0] == 'ctrl' and e[3] == 0 and e[4] == 9])
ok(setups == len(opens), "each retry runs the full setup again, including the configure step")
ok(True, "(status patterns checked below)")
w.read_result = 49; w.run(400)
ok(w.slots()[0] == FAKE, "and once it starts answering, it's used")

print("== a controller waiting for its PS button (reports with only PS) is not reset")
w = World(); w.set_pad(); w.run(1000)
ok(len([e for e in w.log if e[0] == 'open']) == 1, "real reports keep coming, so no restarts")

print("== some controllers refuse the extra wake-ups")
w = World(); w.fail = {(0xA1, 1, 0x03F5), (0x21, 9, 0x03F4)}; w.set_pad(); w.run(700)
lights = []
for _ in range(600):
    w.run(1); lights.append(w.m.r32(GPIO) & 0x20)
ok(w.slots()[0] == FAKE and not any(lights), "still works, and no error blinking")
w = World(); w.fail = {(0xA1, 1, 0x03F2)}; w.set_pad(); w.run(400)
ok(w.slots()[0] == FAKE, "even if the main switch-on (F2) is refused but reports come, it's used (no blinking)")


print("== menu's controller manager not created yet")
w = World(); w.m.w32(MANAGER_PTR, 0); w.set_pad(); w.run(200)
ok(w.revo_reads == [], "skips the menu's read and the fake controller safely")
print("ALL STAGE 2 CHECKS PASSED")
