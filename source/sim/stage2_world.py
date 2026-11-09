import struct, sys
sys.path.insert(0, '.')
from ppcsim import Mem, CPU

BASE = 0x80001800
IOS_OPEN, IOS_CLOSE, IOCTLV, IOCTLV_ASYNC, IOCTL = 0x81572B10, 0x81572CF0, 0x815737F8, 0x81573714, 0x815734A8
IOCTL_ASYNC, DCFLUSH, DCINVAL = 0x81573370, 0x8152D934, 0x8152D908
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

class World:
    def __init__(self, plugged=True, oh0='plugged', hid=True):
        self.m = Mem(); self.c = CPU(self.m)
        self.m.load(BASE, code); self.m.fill(BASE + len(code), 0x3000 - 0x1800 - len(code))
        self.m.fill(0x817F0000, 0x10000)                 # stack
        self.m.fill(MANAGER, 16); self.m.w32(MANAGER_PTR, MANAGER)
        self.m.w32(GPIO, 0xC100)
        self.plugged = plugged; self.remotes = [False] * 4
        self.oh0 = oh0 if plugged else 'absent'; self.hid = hid; self.hid_version = 0x40001
        self.hid_list = []; self.list_req = None; self.list_first = True; self.list_ready = False
        self.hid_pending = None; self.hid_ctrl = []; self.hid_result = 0; self.cache_ops = []
        self.pending = None; self.report = bytes(53); self.read_result = 49
        self.log = []; self.revo_reads = []; self.frame = 0; self.opened = 0
        self.cfg = 0; self.fail = set(); self.sent = {}
        self.needs_config = False; self.dev_configured = False; self.unconfigured_read = 0
        self.dev_suspended = False
        self.open_err = -6; self.listed = False; self.root_open = False; self.devlist_calls = []
        c = self.c
        c.stubs = {IOS_OPEN: self.ios_open, IOS_CLOSE: self.ios_close, IOCTLV: self.ioctlv,
                   IOCTLV_ASYNC: self.ioctlv_async, MGRREAD: self.mgrread, REVOREAD: self.revoread, IOCTL: self.ioctl,
                   IOCTL_ASYNC: self.ioctl_async, DCFLUSH: self.dcflush, DCINVAL: self.dcinval}
    def ios_open(self, c):
        path = bytes(self.m.r8(c.r[3] + i) for i in range(40)).split(b'\0')[0]
        if path == b'/dev/usb/oh0':
            (None if getattr(self,'quiet_root',False) else self.log.append(('rootopen', self.frame))); self.root_open = True; c.r[3] = 3; return
        if path == b'/dev/usb/hid':
            self.log.append(('hidopen', self.frame)); c.r[3] = 7 if self.hid else (-6 & 0xFFFFFFFF); return
        if path in (b'/dev/usb/oh0/54c/9cc', b'/dev/usb/oh0/54c/5c4'):
            self.log.append(('open4', self.frame, path[-3:])); return self.ds4_open(c, path)
        assert path == b'/dev/usb/oh0/54c/268', path
        self.log.append(('open', self.frame))
        c.r[3] = {'plugged': 5, 'claimed': -2 & 0xFFFFFFFF, 'absent': self.open_err & 0xFFFFFFFF}[self.oh0]
    def ds4_open(self, c, path):
        c.r[3] = -6 & 0xFFFFFFFF          # no PS4 controller in the PS3 tests
    def ioctl(self, c):
        self.log.append(('ioctl', self.frame, c.r[3], c.r[4], c.r[5], c.r[6], c.r[7], c.r[8]))
        if c.r[3] == 7:
            if c.r[4] == 6:
                mode = getattr(self, 'ver_mode', 'return')
                has_buf = c.r[7] != 0 and c.r[8] == 32
                if mode == 'return': c.r[3] = self.hid_version
                elif mode == 'buffer':
                    if has_buf: self.m.w32(c.r[7], self.hid_version); c.r[3] = 0
                    else: c.r[3] = -4 & 0xFFFFFFFF
                elif mode == 'error': c.r[3] = -4 & 0xFFFFFFFF
                return
            assert c.r[4] == 2 and c.r[6] == 32 and c.r[7] == 0 and c.r[8] == 0 and c.r[5] % 32 == 0
            req = self.read_req(c.r[5]); self.hid_ctrl.append((self.frame,) + req)
            dev, rt, rq, val, idx, ln, data = req
            if rt & 0x80 and ln: self.m.w8(data, 0x5A)
            c.r[3] = 0; return
        if c.r[4] == 6: self.dev_suspended = False
        c.r[3] = 0
    def read_req(self, a):
        m = self.m
        return (m.r32(a + 0x10), m.r8(a + 0x14), m.r8(a + 0x15), m.r16(a + 0x16), m.r16(a + 0x18), m.r16(a + 0x1A), m.r32(a + 0x1C))
    def ioctl_async(self, c):
        assert c.r[3] == 7
        if c.r[4] == 0:
            assert self.list_req is None, "two device-list requests at once"
            assert c.r[5] == 0 and c.r[6] == 0 and c.r[8] == 0x600 and c.r[7] % 32 == 0
            self.list_req = (c.r[9], c.r[10], c.r[7])
            if self.list_first: self.list_first = False; self.list_ready = True
            c.r[3] = 0; return
        assert c.r[4] == 2 and c.r[6] == 32 and self.hid_pending is None and self.pending is None
        req = self.read_req(c.r[5])
        assert req[1:6] == (0xA1, 0x01, 0x0101, 0, 53), req
        self.hid_pending = (c.r[9], c.r[10], req)
        self.log.append(('hidread', self.frame, req[0])); c.r[3] = 0
    def dcflush(self, c): self.cache_ops.append(('flush', c.r[3], c.r[4]))
    def dcinval(self, c): self.cache_ops.append(('inval', c.r[3], c.r[4]))
    def hid_change(self, devices):
        self.hid_list = devices; self.list_ready = True
    def build_list(self, out):
        off = 0
        for devno, vid, pid, le in self.hid_list:
            e = bytearray(0x44)
            e[0:4] = (0x44).to_bytes(4, 'big'); e[4:8] = devno.to_bytes(4, 'big')
            e[8:12] = bytes([0x12, 0x01, 0x02, 0x00])
            vp = vid.to_bytes(2, 'little') + pid.to_bytes(2, 'little') if le else vid.to_bytes(2, 'big') + pid.to_bytes(2, 'big')
            e[16:20] = vp
            for i, b in enumerate(e): self.m.w8(out + off + i, b)
            off += 0x44
        self.m.w32(out + off, 0xFFFFFFFF)
    def ios_close(self, c):
        if c.r[3] == 3: self.root_open = False
        self.log.append(('close', self.frame, c.r[3])); c.r[3] = 0
    def vecs(self, c):
        v = c.r[7]
        return [(self.m.r32(v + 8 * i), self.m.r32(v + 8 * i + 4)) for i in range(7)]
    def msg(self, c):
        vs = self.vecs(c); m = self.m
        rt, rq = m.r8(vs[0][0]), m.r8(vs[1][0])
        val = m.r8(vs[2][0]) | m.r8(vs[2][0] + 1) << 8
        ln = m.r8(vs[4][0]) | m.r8(vs[4][0] + 1) << 8
        assert [l for _, l in vs[:6]] == [1, 1, 2, 2, 2, 1] and vs[6][1] == ln and vs[6][0] % 32 == 0
        assert (c.r[4], c.r[5], c.r[6]) == (0, 6, 1)
        return (rt, rq, val, ln), vs[6]
    def ioctlv(self, c):
        assert self.pending is None, "sync message while a read is in flight"
        if c.r[3] == 3:
            assert self.root_open and (c.r[4], c.r[5], c.r[6]) == (12, 2, 2)
            v = c.r[7]; vs = [(self.m.r32(v + 8 * i), self.m.r32(v + 8 * i + 4)) for i in range(4)]
            assert [l for _, l in vs] == [1, 1, 1, 64] and all(b % 32 == 0 for b, _ in vs)
            self.devlist_calls.append((self.m.r8(vs[0][0]), self.m.r8(vs[1][0])))
            entries = [(0x11111111, 0x046D, 0xC52B)] + ([(0x22222222, 0x054C, 0x0268)] if self.listed else [])
            self.m.w8(vs[2][0], len(entries))
            for i, (u, vid, pid) in enumerate(entries):
                self.m.w32(vs[3][0] + 8 * i, u); self.m.w32(vs[3][0] + 8 * i + 4, (vid << 16) | pid)
            c.r[3] = 0; return
        (rt, rq, val, ln), buf = self.msg(c)
        self.log.append(('ctrl', self.frame, c.r[3], rt, rq, val, ln))
        self.sent[(rt, rq, val)] = bytes(self.m.r8(buf[0] + i) for i in range(ln))
        if (rt, rq) == (0x80, 0x08): self.m.w8(buf[0], self.cfg)
        if (rt, rq) == (0x00, 0x09): self.dev_configured = True
        c.r[3] = (-4 & 0xFFFFFFFF) if (rt, rq, val) in self.fail else 0
    def ioctlv_async(self, c):
        if c.r[3] == 3:                       # a root-hub hook (stage 3): just leave it waiting
            (None if getattr(self,'quiet_root',False) else self.log.append(('hook', self.frame, c.r[4]))); c.r[3] = 0; return
        assert self.pending is None, "two reads in flight"
        (rt, rq, val, ln), buf = self.msg(c)
        assert (rt, rq, val, ln) == (0xA1, 0x01, 0x0101, 53), (rt, rq, val, ln)
        self.pending = (c.r[8], c.r[9], buf)
        self.log.append(('read', self.frame, c.r[3])); c.r[3] = 0
    def mgrread(self, c):
        assert c.r[3] == MANAGER
        for i in range(4):
            v = self.m.r32(MANAGER + 4 * i)
            assert v != S + 0x84, "fake controller still in a slot during the menu's read"
            self.m.w32(MANAGER + 4 * i, REAL_REMOTE + i * 0x40 if self.remotes[i] else 0)
    def revoread(self, c):
        obj = c.r[3]; m = self.m
        assert m.r32(obj) == 0x816347F4 and m.r32(obj + 0x20) == KPAD and m.r32(obj + 0x10) == 0xFFFFFFFF
        k = KPAD
        self.revo_reads.append(dict(frame=self.frame, chan=m.r32(obj + 0x14), hold=m.r32(k), trig=m.r32(k + 4),
            release=m.r32(k + 8), x=fl(m, k + 0x20), y=fl(m, k + 0x24), hx=fl(m, k + 0x34), hy=fl(m, k + 0x38),
            err=m.r8(k + 0x5D), dpd=m.r8(k + 0x5E)))
    def complete_read(self):
        if self.list_req and self.list_ready:
            cb, arg, out = self.list_req; self.list_req = None; self.list_ready = False
            self.build_list(out)
            self.c.r[3] = 0; self.c.r[4] = arg; self.c.r[1] = 0x817E0000; self.c.call(cb)
        if self.hid_pending:
            cb, arg, req = self.hid_pending; self.hid_pending = None
            res = self.hid_result
            if res >= 0 and self.hid_list and any(d[1:3] == (0x054C, 0x0268) for d in self.hid_list):
                for i in range(53): self.m.w8(req[6] + i, self.report[i] if i < len(self.report) else 0)
            self.c.r[3] = res & 0xFFFFFFFF; self.c.r[4] = arg; self.c.r[1] = 0x817E0000; self.c.call(cb)
        # the IPC interrupt: IOS has written the report, then calls our callback
        if not self.pending: return
        cb, arg, buf = self.pending; self.pending = None
        res = self.read_result
        if self.needs_config and not self.dev_configured: res = self.unconfigured_read
        if self.dev_suspended: res = -4
        if res > 0:
            for i in range(min(53, buf[1])): self.m.w8(buf[0] + i, self.report[i] if i < len(self.report) else 0)
        self.c.r[3] = res & 0xFFFFFFFF; self.c.r[4] = arg; self.c.r[1] = 0x817E0000
        self.c.call(cb)
        assert self.c.r[3] == 0
    def run(self, n, complete=True):
        c = self.c; saved = [0x1000 + i for i in range(32)]
        for _ in range(n):
            self.frame += 1
            for i in range(32): c.r[i] = saved[i]
            c.r[1] = 0x817FFF00; c.msr = 0x8032
            for i in range(14, 32): c.f[i] = float(i)
            c.call(BASE)
            for i in list(range(13, 32)) + [1, 2]:
                assert c.r[i] == (0x817FFF00 if i == 1 else saved[i]), "r%d not preserved" % i
            for i in range(14, 32): assert c.f[i] == float(i), "f%d not preserved" % i
            assert c.msr == 0x8032 and self.m.r32(GPIO) & ~0x20 == 0xC100
            if complete: self.complete_read()
    def slots(self): return [self.m.r32(MANAGER + 4 * i) for i in range(4)]
    def set_pad(self, b2=0, b3=0, b4=0, lx=128, ly=128):
        r = bytearray(53); r[0] = 1; r[2], r[3], r[4] = b2, b3, b4; r[6], r[7], r[8], r[9] = lx, ly, 128, 128
        self.report = bytes(r)

