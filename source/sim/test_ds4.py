# PS4 (DualShock 4) tests: a wired PS4 controller on /dev/usb/oh0/54c/9cc (CUH-ZCT2)
# or /54c/5c4 (CUH-ZCT1). Its reports come from interrupt endpoint 0x84 (ioctlv 2).
#   ./build.sh && cd sim && python3 test_ds4.py
#   CFLAGS=-DDIAG ../build.sh && python3 test_ds4.py diag     (blink-code build)
import sys
sys.path.insert(0, '.')
from stage3_world import *
FAKE = S + 0x84
DIAG = 'diag' in sys.argv

def ok(cond, msg):
    if not cond: raise AssertionError(msg)
    print("   ok  ", msg)

def ds4_descriptor(hid_ep=0x84):
    """a DualShock 4-like configuration: audio interfaces (with an isochronous IN
    endpoint that must be skipped), then the HID interface with its endpoints"""
    d = bytearray()
    d += bytes([9, 4, 0, 0, 0, 1, 1, 0, 0])            # interface 0: audio control
    d += bytes([9, 4, 2, 1, 1, 1, 2, 0, 0])            # interface 2 alt 1: audio streaming
    d += bytes([7, 5, 0x82, 0x05, 0x84, 0x00, 1])      # endpoint 0x82 IN isochronous (not ours)
    d += bytes([9, 4, 3, 0, 2, 3, 0, 0, 0])            # interface 3: HID
    d += bytes([9, 0x21, 0x11, 0x01, 0, 1, 0x22, 0xFB, 0x01])
    d += bytes([7, 5, hid_ep, 0x03, 0x40, 0x00, 5])    # HID interrupt IN
    d += bytes([7, 5, 0x03, 0x03, 0x40, 0x00, 5])      # HID interrupt OUT
    total = 9 + len(d)
    return bytes([9, 2, total & 0xFF, total >> 8, 4, 1, 0, 0xC0, 0xFA]) + d

class World4(World3):
    """intr: 'ok' / 'error' / 'hang' for interrupt reads; get: 'ok' / 'error' / 'hang' for GET_REPORT reads.
    sdk_quirk: like the Wii Menu's IOS_IoctlvAsync, a background ioctlv leaves its output buffers'
    addresses converted to physical (addr - 0x80000000) after it finishes; IOS answers -1 to a
    request whose buffer address isn't a proper one."""
    def __init__(self, ds4='9cc', ds3=False, ds4_state='plugged', intr='ok', get='error', desc='ok', hid_ep=0x84, **kw):
        super().__init__(present=ds3, **kw)
        self.ds4 = ds4; self.ds4_state = ds4_state if ds4 else 'absent'
        self.intr, self.get, self.desc, self.hid_ep = intr, get, desc, hid_ep
        self.ds4_open_fd = False; self.ds4_report = None; self.set_ds4(); self.stale = []
        self.desc_err = -7004; self.read_err = -7004; self.cleared = False; self.clear_result = 0
    def ds4_open(self, c, path):
        if self.ds4_state == 'plugged' and path.endswith(self.ds4.encode()):
            self.ds4_open_fd = True; c.r[3] = 6
        elif self.ds4_state == 'claimed' and path.endswith(self.ds4.encode()):
            c.r[3] = -2 & 0xFFFFFFFF
        else:
            c.r[3] = -6 & 0xFFFFFFFF
    # --- plug-in (hooks): the IOS grabber takes a newly appearing PS4 unless we open it first
    def ds4pid(self): return {'9cc': 0x09CC, '5c4': 0x05C4}.get(self.ds4)
    def present_id(self, pid):
        return super().present_id(pid) or (pid == self.ds4pid() and self.ds4_state != 'absent')
    def async_open4(self, idstr):
        if idstr.decode() != self.ds4 or self.ds4_state == 'absent': return -6
        if self.ds4_state == 'claimed' or self.ds4_open_fd: return -2
        self.ds4_open_fd = True; return 6
    def close_async(self, c):
        if c.r[3] == 6: self.ds4_open_fd = False
        super().close_async(c)
    def unplug4(self): self.ds4_state = 'absent'
    def plug4(self):
        self.ds4_state = 'appearing'
        pid = self.ds4pid()
        if pid in self.hookmap:
            cb, arg = self.hookmap.pop(pid); self.callback(cb, 0, arg); self.drain()
        self.ds4_state = 'plugged' if self.ds4_open_fd else 'claimed'
    def ios_close(self, c):
        if c.r[3] == 6:
            self.ds4_open_fd = False
            if self.pending and len(self.pending) == 4:      # IOS cancels a waiting read on close: its answer comes later
                self.stale.append(self.pending); self.pending = None
        super().ios_close(c)
    def ioctlv(self, c):
        if c.r[3] != 6: return super().ioctlv(c)
        if c.r[4] == 2:                          # interrupt OUT: the light bar
            assert self.pending is None, "light bar sent while a read is in flight"
            v = c.r[7]; vs = [(self.m.r32(v + 8 * i), self.m.r32(v + 8 * i + 4)) for i in range(3)]
            assert (c.r[5], c.r[6]) == (2, 1) and [l for _, l in vs] == [1, 2, 32]
            assert self.m.r8(vs[0][0]) == 0x03 and self.m.r16(vs[1][0]) == 32, "OUT endpoint 0x03, 32 bytes"
            assert all(b % 32 == 0 for b, _ in vs), "each buffer on its own line"
            d = bytes(self.m.r8(vs[2][0] + i) for i in range(32))
            assert d[0] == 0x05 and d[4:6] == b'\0\0', "report 0x05, no rumble"
            self.bars = getattr(self, 'bars', []) + [(self.frame, tuple(d[6:9]))]
            self.log.append(('bar', self.frame)); c.r[3] = 32; return
        (rt, rq, val, ln), buf = self.msg(c)
        super().ioctlv(c)
        if (rt, rq) == (0x80, 0x06):
            assert val == 0x200 and buf[0] % 32 == 0 and buf[1] in (64, 256) and ln == buf[1]
            if self.desc == 'error': c.r[3] = self.desc_err & 0xFFFFFFFF; return
            d = ds4_descriptor(self.hid_ep)[:ln]
            for i, b in enumerate(d): self.m.w8(buf[0] + i, b)
            c.r[3] = len(d)
        elif (rt, rq) in ((0x80, 0x08), (0x00, 0x09)):
            pass
        elif (rt, rq) == (0x02, 0x01):
            vs = self.vecs(c); idx = self.m.r8(vs[3][0]) | self.m.r8(vs[3][0] + 1) << 8
            assert val == 0 and idx == 0x84, "CLEAR_FEATURE ENDPOINT_HALT on 0x84"
            self.cleared = True; c.r[3] = self.clear_result & 0xFFFFFFFF
        else:
            raise AssertionError("PS4 got a PS3 setup message %r" % ((rt, rq, val),))
    sdk_quirk = True                 # what the real Wii does (PS4 test 5)
    def ioctlv_async(self, c):
        if self.sdk_quirk and c.r[3] in (5, 6):
            v, nin, nio = c.r[7], c.r[5], c.r[6]
            bases = [self.m.r32(v + 8 * i) for i in range(nin + nio)]
            self.io_vecs = [v + 8 * i for i in range(nin, nin + nio)]
            if any(b < 0x80000000 for b in bases):
                assert self.pending is None, "two reads in flight"
                self.pending = (c.r[8], c.r[9], (0, 0), 'bad'); self.log.append(('badaddr', self.frame)); c.r[3] = 0
                return
        return self.ioctlv_async2(c)
    def quirk_done(self):
        if self.sdk_quirk:
            for a in getattr(self, 'io_vecs', []): self.m.w32(a, (self.m.r32(a) - 0x80000000) & 0xFFFFFFFF)
            self.io_vecs = []
    def ioctlv_async2(self, c):
        if c.r[3] != 6: return super().ioctlv_async(c)
        assert self.pending is None, "two reads in flight"
        cmd, nin, nio, v = c.r[4], c.r[5], c.r[6], c.r[7]
        vs = [(self.m.r32(v + 8 * i), self.m.r32(v + 8 * i + 4)) for i in range(nin + nio)]
        if cmd == 2:
            assert (nin, nio) == (2, 1) and [l for _, l in vs] == [1, 2, 64] and vs[2][0] % 32 == 0
            assert self.m.r8(vs[0][0]) == self.hid_ep and self.m.r16(vs[1][0]) == 64, \
                "endpoint %#x (want %#x), 64 bytes" % (self.m.r8(vs[0][0]), self.hid_ep)
            self.pending = (c.r[8], c.r[9], vs[2], 'intr'); self.log.append(('iread', self.frame))
        else:
            (rt, rq, val, ln), buf = self.msg(c)
            vs = self.vecs(c); idx = self.m.r8(vs[3][0]) | self.m.r8(vs[3][0] + 1) << 8
            assert (rt, rq, val, ln, idx) == (0xA1, 0x01, 0x0101, 64, 3), (rt, rq, val, ln, idx)
            self.pending = (c.r[8], c.r[9], buf, 'get'); self.log.append(('gread', self.frame))
        c.r[3] = 0
    def complete_read(self):
        self.drain()
        for cb, arg, buf, kind in self.stale:          # cancelled reads answer late, with an error
            self.callback(cb, -1, arg); assert self.c.r[3] == 0
        self.stale = []
        if self.pending and len(self.pending) == 4 and self.pending[3] == 'bad':
            cb, arg, buf, kind = self.pending; self.pending = None
            self.callback(cb, -1, arg); assert self.c.r[3] == 0
            return
        if self.pending and len(self.pending) == 4:
            cb, arg, buf, kind = self.pending
            mode = self.intr if kind == 'intr' else self.get
            if mode != 'hang': self.quirk_done()
            if mode == 'hang': return
            self.pending = None
            res = self.ds4_result if mode == 'ok' else self.read_err
            if self.ds4_state not in ('plugged', 'appearing'): res = -7004
            if res > 0:
                for i in range(64): self.m.w8(buf[0] + i, self.ds4_report[i])
            self.callback(cb, res, arg); assert self.c.r[3] == 0
            return
        super().complete_read()
    def set_ds4(self, hat=8, b5=0, b6=0, b7=0, lx=128, ly=128, rid=1):
        r = bytearray(64); r[0] = rid; r[1], r[2], r[3], r[4] = lx, ly, 128, 128
        r[5] = (b5 & 0xF0) | hat; r[6] = b6; r[7] = b7
        self.ds4_report = bytes(r); self.ds4_result = 64

def ctrls(w, fd):
    return [(e[3], e[4], e[5]) for e in w.log if e[0] == 'ctrl' and e[2] == fd]

if not DIAG:
    print("== cold boot, PS4 controller (CUH-ZCT2) plugged in, no PS3 controller")
    w = World4(ds4='9cc'); w.run(130)
    ok(w.slots()[0] == FAKE, "PS4 controller works as a Wii Remote")
    ok(ctrls(w, 6) == [(0x80, 0x08, 0), (0x00, 0x09, 1), (0x80, 0x06, 0x200)], "setup: GET/SET_CONFIGURATION, read descriptor; no PS3 wake-up or LED (%s)" % ctrls(w, 6))
    ok(any(e[0] == 'iread' for e in w.log), "reads go to interrupt endpoint 0x84")
    w.run(70)
    ok([b[1] for b in w.bars] == [(0xFF, 0, 0)] * 2 and w.bars[1][0] - w.bars[0][0] == 60, "light bar set red at setup, and again 1 s later (%s)" % w.bars)
    w.set_ds4(lx=255); w.run(20); ok(w.revo_reads[-1]['x'] > 0.5, "left stick right -> pointer right")
    w.set_ds4(ly=0); w.run(20); ok(w.revo_reads[-1]['y'] < 0.5, "left stick up -> pointer up")
    w.set_ds4(lx=128, ly=128); x = w.revo_reads[-1]['x']; w.run(10)
    ok(abs(w.revo_reads[-1]['x'] - x) < 1e-6, "stick centred -> pointer stays")

    print("== buttons")
    cases = [(dict(b5=0x20), 0x0800, "Cross = A"), (dict(b5=0x40), 0x0400, "Circle = B"),
             (dict(b5=0x10), 0x0200, "Square = 1"), (dict(b5=0x80), 0x0100, "Triangle = 2"),
             (dict(b6=0x01), 0x1000, "L1 = -"), (dict(b6=0x10), 0x1000, "Share = -"),
             (dict(b6=0x02), 0x0010, "R1 = +"), (dict(b6=0x20), 0x8000, "Options = HOME"),
             (dict(b7=0x01), 0x8000, "PS = HOME"),
             (dict(b6=0x04 | 0x08 | 0x40 | 0x80, b7=0x02 | 0xFC), 0, "L2, R2, L3, R3, touchpad, counter bits: nothing")]
    for kw, want, name in cases:
        w.set_ds4(**kw); w.run(2); ok(w.revo_reads[-1]['hold'] == want, name)
    dirs = [0x8, 0xA, 0x2, 0x6, 0x4, 0x5, 0x1, 0x9]   # up, up-right, right, down-right, down, down-left, left, up-left
    for hat, want in enumerate(dirs):
        w.set_ds4(hat=hat); w.run(2)
        ok(w.revo_reads[-1]['hold'] == want, "D-pad hat %d -> %#x" % (hat, want))
    w.set_ds4(hat=8); w.run(2); ok(w.revo_reads[-1]['hold'] == 0, "D-pad released")
    n = len(w.revo_reads); w.set_ds4(b5=0x20); w.run(4)
    ok([r['trig'] for r in w.revo_reads[n:]].count(0x0800) == 1, "a press counts as a new press exactly once")
    ok(w.revo_reads[-1]['trig'] == 0 and w.revo_reads[-1]['hold'] == 0x0800, "then held")
    n = len(w.revo_reads); w.set_ds4(); w.run(4)
    ok([r['release'] for r in w.revo_reads[n:]].count(0x0800) == 1, "and released once")

    print("== reads that fail or never answer")
    w = World4(intr='error'); w.run(600)
    ok(FAKE not in w.slots() and len([e for e in w.log if e[0] == 'open4']) >= 3, "reads fail: keeps setting it up again, no crash")
    ok(not any(e[0] == 'gread' for e in w.log), "always interrupt reads (GET_REPORT never worked on the Wii)")
    w.intr = 'ok'; w.run(300); ok(w.slots()[0] == FAKE, "starts working once reads succeed")
    w = World4(intr='hang'); w.run(1500)
    ok(FAKE not in w.slots() and len([e for e in w.log if e[0] == 'open4']) >= 4, "read never answers: keeps reopening, no crash")

    print("== the input endpoint comes from the descriptor")
    w = World4(hid_ep=0x83); w.run(130); ok(w.slots()[0] == FAKE, "HID endpoint 0x83 used (audio endpoint 0x82 skipped)")
    w = World4(desc='error'); w.run(130); ok(w.slots()[0] == FAKE, "no descriptor: 0x84 assumed, works")

    print("== other report IDs are ignored")
    w = World4(); w.run(130); w.set_ds4(b5=0x20, rid=0x11); w.run(5)
    ok(w.revo_reads[-1]['hold'] == 0, "report 0x11 doesn't press anything")

    print("== original PS4 controller (CUH-ZCT1)")
    w = World4(ds4='5c4'); w.run(130); ok(w.slots()[0] == FAKE, "works")
    ok([e[2] for e in w.log if e[0] == 'open4'][:2] == [b'9cc', b'5c4'], "tries the ZCT2 ID, then the ZCT1 ID")

    print("== both PS3 and PS4 plugged in: the PS3 controller is used, as before")
    w = World4(ds4='9cc', ds3=True); w.set_pad(); w.run(130)
    ok(w.slots()[0] == FAKE and not w.ds4_open_fd, "PS3 opened, PS4 left alone")
    w.set_pad(0, 0x40); w.run(2); ok(w.revo_reads[-1]['hold'] == 0x0800, "PS3 Cross = A")

    print("== PS3 and PS4 plugged in together")
    w = World4(ds4='9cc', ds3=True); w.set_pad(); w.run(150)
    ok(w.slots()[0] == FAKE and not w.ds4_open_fd, "the PS3 controller is used")
    w.unplug(); w.run(150)
    ok(w.ds4_open_fd and w.slots()[0] == FAKE, "PS3 unplugged: the PS4 takes over (within %.1f s)" % (([e[1] for e in w.log if e[0] == 'open4'][-1] - 150) / 60))
    w = World4(ds4='9cc', ds3=True); w.set_pad(); w.run(150); w.unplug4(); w.run(60)
    ok(w.slots()[0] == FAKE, "PS4 unplugged while the PS3 is used: PS3 carries on")

    print("== PS4 unplugged and plugged back in")
    w = World4(); w.run(130); w.ds4_state = 'absent'; w.run(140)
    ok(FAKE not in w.slots() and not w.ds4_open_fd, "gone, handle closed")
    w.ds4_state = 'plugged'; w.set_ds4(); w.run(200); ok(w.slots()[0] == FAKE, "back within a few seconds")

    print("== plug-in hooks for the PS4 controllers")
    w = World4(ds4=None); w.run(3)
    ok(sorted(h[2] for h in w.hooks4) == [0x05C4, 0x09CC] and w.hooks[0][1] == 30, "PS3, ZCT2 and ZCT1 hooks all waiting from the start")
    w = World4(ds4='5c4', ds4_state='claimed'); w.run(300)
    ok(FAKE not in w.slots(), "ZCT1 taken by IOS at boot (like your Wii): not working")
    w.unplug4(); w.run(30); w.plug4(); w.run(3)
    ok(w.ds4_open_fd and w.ds4_state == 'plugged', "replugged at the menu: opened from the hook, before IOS takes it")
    ok(w.slots()[0] == FAKE, "and working right away")
    w.set_ds4(b5=0x20); w.run(3); ok(w.revo_reads[-1]['hold'] == 0x0800, "Cross = A")
    w = World4(ds4='9cc', ds4_state='absent'); w.run(300); w.plug4(); w.run(3)
    ok(w.slots()[0] == FAKE, "ZCT2 plugged in at the menu: works")
    w = World4(ds4='9cc'); w.run(150); ok(w.slots()[0] == FAKE, "working")
    w.unplug4(); w.run(10); w.plug4(); w.run(3)
    ok(w.ds4_open_fd and w.slots()[0] == FAKE, "unplug and replug while working: back right away")
    w = World4(ds4='9cc', ds4_state='absent'); w.run(5); w.plug4(); w.run(50)
    ok(w.ds4_open_fd and FAKE not in w.slots(), "plugged in during the first 2 s: grabbed, set up at 2 s")
    w.run(80); ok(w.slots()[0] == FAKE, "then working")
    w = World4(ds4='9cc', ds4_state='absent', ds3=True); w.set_pad(); w.run(150)
    ok(w.slots()[0] == FAKE, "PS3 working"); w.plug4(); w.run(5)
    ok(not w.ds4_open_fd, "a PS4 plugged in while the PS3 works: left alone")
    w = World4(ds4='9cc', ds4_state='absent', hook30=False); w.run(400)
    ok(any(h[1] == 27 for h in w.hooks4), "no ioctlv 30: PS4 hooks fall back to 27 too")

    print("== a real Wii Remote is player 1")
    w = World4(); w.remotes[0] = True; w.run(130)
    ok(w.slots()[0] == REAL_REMOTE and w.slots()[1] == FAKE, "PS4 controller takes slot 2")

    print("== no controller at all: no USB traffic beyond the open attempts")
    w = World4(ds4=None); w.run(400)
    ok(not any(e[0] in ('ctrl', 'iread', 'read') for e in w.log), "nothing sent")
    ok(w.m.r32(GPIO) & 0x20 == 0, "disc light untouched")
    print("ALL PS4 TESTS PASSED")
else:
    class Seq(World4):
        """interrupt reads: good `goods` times after each setup, then fail with `after` (code or 'hang')
        unless `fix` applies: 'clear' = a CLEAR_FEATURE(HALT) makes the next reads good again,
        'pause' = reads are good when sent >= 5 frames after the previous one finished.
        GET_REPORT (interface 3): `get` = 'ok', 'hang' or an error code."""
        def __init__(self, goods=1, after=-1, get=-7004, fix=None, **kw):
            super().__init__(**kw); self.goods, self.after, self.getmode, self.fix = goods, after, get, fix
            self.n = 0; self.last_done = -99; self.sent_at = 0
        def ds4_open(self, c, path):
            super().ds4_open(c, path); self.n = 0; self.cleared = False
        def ioctlv_async(self, c):
            super().ioctlv_async(c)
            if c.r[3] == 0: self.sent_at = self.frame
        def complete_read(self):
            if self.pending and len(self.pending) == 4:
                if self.pending[3] == 'intr':
                    self.n += 1
                    good = self.n <= self.goods
                    if self.fix == 'clear' and self.cleared: good = True
                    if self.fix == 'pause' and self.sent_at - self.last_done >= 5: good = True
                    if good: self.intr = 'ok'
                    elif self.after == 'hang': self.intr = 'hang'
                    else: self.intr = 'error'; self.read_err = self.after
                    if self.intr != 'hang': self.last_done = self.frame
                else:
                    if self.getmode in ('ok', 'hang'): self.get = self.getmode
                    else: self.get = 'error'; self.read_err = self.getmode
            super().complete_read()
    def lights(w, frames):
        out = [0]                          # out[f] = frame f
        for _ in range(frames): w.run(1); out.append(1 if w.m.r32(GPIO) & 0x20 else 0)
        return out
    def numbers(rec, start=300):
        """decode one full repeat of the blinked numbers (short blinks = digit, long blink = 0)"""
        runs = []; i = start
        while i < len(rec):
            j = i
            while j < len(rec) and rec[j] == rec[i]: j += 1
            runs.append((rec[i], j - i)); i = j
        k = next(k for k, (v, n) in enumerate(runs) if v == 0 and n >= 380) + 1
        nums, digits, d = [], [], 0
        for v, n in runs[k:]:
            if v == 1:
                if n >= 30: digits.append(0); d = None
                else: d = (d or 0) + 1
            else:
                if n < 30: continue
                if d: digits.append(d)
                d = 0
                if n >= 120:
                    nums.append(7777 if digits == [0, 0] else int(''.join(map(str, digits))) if digits else None); digits = []
                if n >= 380: break
        return nums
    print("== blink codes (test build 8)")
    w = World4(ds4=None); rec = lights(w, 7600)
    ok(not any(rec[:300]), "nothing in the first 5 s")
    ok(numbers(rec) == [1], "no controller: 1 (%s)" % numbers(rec))
    ok(not any(rec[7500:]), "stops after 2 minutes, light off again")
    w = World4(ds4='5c4', ds4_state='claimed'); rec = lights(w, 2000)
    ok(numbers(rec) == [3, 2], "taken by IOS at boot, hooks waiting: 3 2 (%s)" % numbers(rec))
    w = World4(ds4='5c4', ds4_state='claimed', hook30=False, hook27=False); rec = lights(w, 2000)
    ok(numbers(rec) == [3, 1], "taken, and no hooks could be set up: 3 1 (%s)" % numbers(rec))
    w = World4(ds4=None, ds3=True); w.read_result = -4; w.set_pad(); rec = lights(w, 2000)
    ok(numbers(rec) == [2], "PS3 controller found but silent: 2 (%s)" % numbers(rec))
    w = World4(ds4='5c4', ds4_state='claimed'); lights(w, 700); w.unplug4(); lights(w, 30); w.plug4(); rec = lights(w, 600)
    ok(w.slots()[0] == FAKE and rec[-1] == 0, "replugged: works, blinking stops, light back off")
    w = World4(ds4='9cc'); rec = lights(w, 7600)
    ok(sum(rec) == 60 and w.slots()[0] == FAKE, "PS4 working: just the 1 s glow")
    w = World4(ds4=None, ds3=True); w.set_pad(); rec = lights(w, 7600)
    ok(sum(rec) == 60 and rec[-1] == 0, "PS3 working: the usual 1 s glow")
    w = World4(ds4=None); w.m.w32(GPIO, 0xC100 | 0x20); rec = lights(w, 7600)
    ok(rec[-1] == 1, "light was on before (new message): left on afterwards")
    print("ALL BLINK-NUMBER TESTS PASSED")
