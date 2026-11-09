# Stage 3 world: adds IOS_OpenAsync / IOS_CloseAsync, root-hub insertion hooks
# (ioctlv 30 / 27 on /dev/usb/oh0) and a grabber inside IOS that races us.
from stage2_world import *
OPEN_ASYNC, CLOSE_ASYNC = 0x815729F8, 0x81572C30

class World3(World):
    def __init__(self, present=True, grabber_first=False, hook30=True, hook27=True, **kw):
        super().__init__(plugged=True, oh0='plugged' if present else 'absent', **kw)
        self.c.stubs[OPEN_ASYNC] = self.open_async
        self.c.stubs[CLOSE_ASYNC] = self.close_async
        self.hookmap = {}; self.hook30 = hook30; self.hook27 = hook27
        self.grabber_first = grabber_first; self.grabbed = False
        self.queue = []; self.hooks = []; self.our_fd_open = False
        self.root_ioctlv_sync = 0
    # one waiting hook per PID; .hook is the PS3 controller's (0x0268)
    @property
    def hook(self): return self.hookmap.get(0x0268)
    @hook.setter
    def hook(self, v):
        if v is None: self.hookmap.pop(0x0268, None)
        else: self.hookmap[0x0268] = v
    def ios_open(self, c):
        super().ios_open(c)
        if c.r[3] == 5: self.our_fd_open = True
        if c.r[3] == 5 and (self.grabbed): c.r[3] = -2 & 0xFFFFFFFF
    def open_async(self, c):
        path = bytes(self.m.r8(c.r[3] + i) for i in range(40)).split(b'\0')[0]
        assert path in (b'/dev/usb/oh0/54c/268', b'/dev/usb/oh0/54c/9cc', b'/dev/usb/oh0/54c/5c4'), path
        self.log.append(('aopen', self.frame, path[-3:])); self.queue.append(('open', c.r[5], c.r[6], path[-3:])); c.r[3] = 0
    def close_async(self, c):
        self.log.append(('aclose', self.frame, c.r[3])); self.our_fd_open = False
        self.queue.append(('close', c.r[4], c.r[5])); c.r[3] = 0
    def ios_close(self, c):
        if c.r[3] == 5: self.our_fd_open = False
        super().ios_close(c)
    def ioctlv_async(self, c):
        if c.r[3] != 3: return super().ioctlv_async(c)
        cmd, nin, nio = c.r[4], c.r[5], c.r[6]
        v = c.r[7]; vs = [(self.m.r32(v + 8 * i), self.m.r32(v + 8 * i + 4)) for i in range(nin + nio)]
        assert all(b >= 0x80000000 for b, _ in vs), "hook vector address not set up again"
        vid, pid = self.m.r16(vs[0][0]), self.m.r16(vs[1][0])
        assert vid == 0x054C and pid in (0x0268, 0x09CC, 0x05C4), "VID/PID %04x:%04x" % (vid, pid)
        assert pid not in self.hookmap, "two hooks at once for one ID"
        if pid == 0x0268: self.hooks.append((self.frame, cmd))
        else: self.hooks4 = getattr(self, 'hooks4', []) + [(self.frame, cmd, pid)]
        if cmd == 30:
            assert (nin, nio) == (3, 1) and [l for _, l in vs] == [2, 2, 1, 4]
            assert self.m.r8(vs[2][0]) == 1, "new-only"
            if not self.hook30: self.queue.append(('cb', c.r[8], c.r[9], -4)); c.r[3] = 0; return
        elif cmd == 27:
            assert (nin, nio) == (2, 0) and [l for _, l in vs] == [2, 2]
            if not self.hook27: self.queue.append(('cb', c.r[8], c.r[9], -4)); c.r[3] = 0; return
            if self.present_id(pid): self.queue.append(('cb', c.r[8], c.r[9], 0)); c.r[3] = 0; return
        else: raise AssertionError(cmd)
        self.hookmap[pid] = (c.r[8], c.r[9]); c.r[3] = 0
    def present_id(self, pid):
        return pid == 0x0268 and self.oh0 != 'absent'
    def ioctlv(self, c):
        if c.r[3] == 3: self.root_ioctlv_sync += 1
        return super().ioctlv(c)
    def callback(self, cb, res, arg):
        self.c.r[3] = res & 0xFFFFFFFF; self.c.r[4] = arg; self.c.r[1] = 0x817E0000; self.c.call(cb)
    def drain(self):
        while self.queue:
            q = self.queue.pop(0)
            if q[0] == 'cb': self.callback(q[1], q[3], q[2])
            elif q[0] == 'close': self.callback(q[1], 0, q[2])
            elif q[0] == 'open' and q[3] != b'268':
                r = self.async_open4(q[3])
                self.log.append(('aopen_result', self.frame, r))
                self.callback(q[1], r, q[2])
                continue
            elif q[0] == 'open':
                if self.oh0 == 'absent': r = -6
                elif self.grabbed or self.our_fd_open: r = -2
                else: r = 5; self.our_fd_open = True
                self.log.append(('aopen_result', self.frame, r))
                self.callback(q[1], r, q[2])
    # --- events
    def plug(self):
        """the controller is plugged in (or re-enumerated)"""
        self.oh0 = 'plugged'; self.grabbed = False; self.our_fd_open = False; self.dev_configured = False
        if self.grabber_first: self.grabbed = True
        if self.hook and self.hook27 is not None:
            cb, arg = self.hookmap.pop(0x0268)
            self.callback(cb, 0, arg)   # IPC interrupt: our open goes out from here
            self.drain()
        if not self.grabbed and not self.our_fd_open: self.grabbed = True   # nobody else came: grabber takes it
        elif not self.grabbed and self.grabber_first is False: pass        # we won; grabber gets "in use"
        self.sync_state()
    def sync_state(self):
        self.oh0 = 'claimed' if (self.grabbed and not self.our_fd_open) else self.oh0
    def unplug(self):
        self.oh0 = 'absent'; self.grabbed = False
        self.read_result = -7004
    def complete_read(self):
        self.drain()
        super().complete_read()
        self.drain()
