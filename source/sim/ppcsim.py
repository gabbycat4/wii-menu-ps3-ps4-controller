"""Tiny PowerPC (Broadway subset) interpreter to test the Priiloader hook logic."""
import struct

def sx16(v): return v - 0x10000 if v & 0x8000 else v
def rotl(v, n): n &= 31; return ((v << n) | (v >> (32 - n))) & 0xFFFFFFFF if n else v
def mask(mb, me):
    if mb <= me: m = ((1 << (32 - mb)) - 1) & ~((1 << (31 - me)) - 1)
    else: m = ((1 << (32 - mb)) - 1) | ~((1 << (31 - me)) - 1)
    return m & 0xFFFFFFFF

class Mem:
    def __init__(self): self.b = {}
    def r8(self, a): 
        if a not in self.b: raise Exception("read of unmapped %08x" % a)
        return self.b[a]
    def w8(self, a, v): self.b[a & 0xFFFFFFFF] = v & 0xFF
    def r16(self, a): return (self.r8(a) << 8) | self.r8(a + 1)
    def r32(self, a): return (self.r16(a) << 16) | self.r16(a + 2)
    def w16(self, a, v): self.w8(a, v >> 8); self.w8(a + 1, v)
    def w32(self, a, v): self.w16(a, v >> 16); self.w16(a + 2, v)
    def load(self, a, data):
        for i, x in enumerate(data): self.b[a + i] = x
    def fill(self, a, n, v=0):
        for i in range(n): self.b[a + i] = v

def f32(x):
    try: return struct.unpack('>f', struct.pack('>f', x))[0]
    except OverflowError: return float('inf') if x > 0 else float('-inf')

class CPU:
    def __init__(self, mem):
        self.m = mem; self.r = [0] * 32; self.cr = 0; self.lr = 0; self.msr = 0x8032; self.pc = 0
        self.f = [0.0] * 32; self.ctr = 0; self.ca = 0
        self.stubs = {}; self.mmio_writes = []
    def setcr(self, field, lt, gt, eq):
        v = (8 if lt else 0) | (4 if gt else 0) | (2 if eq else 0)
        sh = 28 - 4 * field
        self.cr = (self.cr & ~(0xF << sh)) | (v << sh)
    def crbit(self, bi): return (self.cr >> (31 - bi)) & 1
    def cmp0(self, v):
        s = v - (1 << 32) if v & 0x80000000 else v
        self.setcr(0, s < 0, s > 0, s == 0)
    def call(self, addr, ret=0xDEAD0000, maxsteps=100000):
        self.lr = ret; self.pc = addr
        for _ in range(maxsteps):
            if self.pc == ret: return
            if self.pc in self.stubs:
                self.stubs[self.pc](self); self.pc = self.lr; continue
            self.step()
        raise Exception("runaway")
    def step(self):
        m, r = self.m, self.r
        ins = m.r32(self.pc); pc = self.pc; npc = pc + 4
        op = ins >> 26; rD = (ins >> 21) & 31; rA = (ins >> 16) & 31; rB = (ins >> 11) & 31
        imm = ins & 0xFFFF; simm = sx16(imm)
        ea = lambda: ((r[rA] if rA else 0) + simm) & 0xFFFFFFFF
        if op == 14: r[rD] = ((r[rA] if rA else 0) + simm) & 0xFFFFFFFF
        elif op == 15: r[rD] = ((r[rA] if rA else 0) + (simm << 16)) & 0xFFFFFFFF
        elif op == 11:
            a = r[rA]; a = a - (1 << 32) if a & 0x80000000 else a
            self.setcr(rD >> 2, a < simm, a > simm, a == simm)
        elif op == 10: self.setcr(rD >> 2, r[rA] < imm, r[rA] > imm, r[rA] == imm)
        elif op == 7: r[rD] = (r[rA] * simm) & 0xFFFFFFFF
        elif op == 8:
            t = (~r[rA] & 0xFFFFFFFF) + (simm & 0xFFFFFFFF) + 1; r[rD] = t & 0xFFFFFFFF; self.ca = t >> 32
        elif op in (12, 13):
            t = r[rA] + (simm & 0xFFFFFFFF); r[rD] = t & 0xFFFFFFFF; self.ca = 1 if t >> 32 else 0
            if op == 13: self.cmp0(r[rD])
        elif op == 16:
            bo, bi = rD, rA; bd = sx16(ins & 0xFFFC)
            if bo & 0x14 == 0x14: take = True
            elif bo & 0x16 == 0x10: self.ctr = (self.ctr - 1) & 0xFFFFFFFF; take = self.ctr != 0
            elif bo & 0x1C == 0x0C: take = self.crbit(bi) == 1
            elif bo & 0x1C == 0x04: take = self.crbit(bi) == 0
            else: raise Exception("bo %d at %08x" % (bo, pc))
            if ins & 1: self.lr = npc
            if take: npc = (pc + bd) & 0xFFFFFFFF
        elif op == 18:
            li = ins & 0x03FFFFFC
            if li & 0x02000000: li -= 0x04000000
            if ins & 1: self.lr = npc
            npc = (pc + li) & 0xFFFFFFFF
        elif op == 19 and ((ins >> 1) & 0x3FF) == 16 and rD == 20: npc = self.lr
        elif op == 19 and ((ins >> 1) & 0x3FF) == 528 and rD == 20:
            if ins & 1: self.lr = npc
            npc = self.ctr
        elif op == 19 and ((ins >> 1) & 0x3FF) == 0:
            src = (self.cr >> (28 - 4 * (rA >> 2))) & 0xF; sh = 28 - 4 * (rD >> 2)
            self.cr = (self.cr & ~(0xF << sh)) | (src << sh)
        elif op == 23:                                  # rlwnm
            mb, me = (ins >> 6) & 31, (ins >> 1) & 31
            r[rA] = rotl(r[rD], r[rB] & 31) & mask(mb, me)
            if ins & 1: self.cmp0(r[rA])
        elif op == 21:
            sh, mb, me = rB, (ins >> 6) & 31, (ins >> 1) & 31
            r[rA] = rotl(r[rD], sh) & mask(mb, me)
            if ins & 1: self.cmp0(r[rA])
        elif op == 20:
            sh, mb, me = rB, (ins >> 6) & 31, (ins >> 1) & 31; mk = mask(mb, me)
            r[rA] = (rotl(r[rD], sh) & mk) | (r[rA] & ~mk & 0xFFFFFFFF)
        elif op == 24: r[rA] = r[rD] | imm
        elif op == 25: r[rA] = r[rD] | (imm << 16)
        elif op == 26: r[rA] = r[rD] ^ imm
        elif op == 27: r[rA] = r[rD] ^ (imm << 16)
        elif op == 29: r[rA] = r[rD] & (imm << 16); self.cmp0(r[rA])
        elif op == 28: r[rA] = r[rD] & imm; self.cmp0(r[rA])
        elif op == 31:
            xo = (ins >> 1) & 0x3FF
            if xo == 444:
                r[rA] = r[rD] | r[rB]
                if ins & 1: self.cmp0(r[rA])
            elif xo == 266: r[rD] = (r[rA] + r[rB]) & 0xFFFFFFFF
            elif xo == 40:
                r[rD] = (r[rB] - r[rA]) & 0xFFFFFFFF
                if ins & 1: self.cmp0(r[rD])
            elif xo == 104: r[rD] = (-r[rA]) & 0xFFFFFFFF
            elif xo == 11: r[rD] = ((r[rA] * r[rB]) >> 32) & 0xFFFFFFFF
            elif xo == 136:
                t = (~r[rA] & 0xFFFFFFFF) + r[rB] + self.ca; r[rD] = t & 0xFFFFFFFF; self.ca = 1 if t >> 32 else 0
            elif xo == 138:
                t = r[rA] + r[rB] + self.ca; r[rD] = t & 0xFFFFFFFF; self.ca = 1 if t >> 32 else 0
            elif xo == 8:
                t = (~r[rA] & 0xFFFFFFFF) + r[rB] + 1; r[rD] = t & 0xFFFFFFFF; self.ca = 1 if t >> 32 else 0
            elif xo == 10:
                t = r[rA] + r[rB]; r[rD] = t & 0xFFFFFFFF; self.ca = 1 if t >> 32 else 0
            elif xo == 202:
                t = r[rA] + self.ca; r[rD] = t & 0xFFFFFFFF; self.ca = 1 if t >> 32 else 0
            elif xo == 234:
                t = r[rA] + 0xFFFFFFFF + self.ca; r[rD] = t & 0xFFFFFFFF; self.ca = 1 if t >> 32 else 0
            elif xo == 26:
                v = r[rD]; n = 0
                while n < 32 and not (v & (0x80000000 >> n)): n += 1
                r[rA] = n
            elif xo == 235: r[rD] = (r[rA] * r[rB]) & 0xFFFFFFFF
            elif xo == 459: r[rD] = (r[rA] // r[rB]) & 0xFFFFFFFF if r[rB] else 0
            elif xo == 24:
                n = r[rB] & 0x3F; r[rA] = (r[rD] << n) & 0xFFFFFFFF if n < 32 else 0
                if ins & 1: self.cmp0(r[rA])
            elif xo == 536:
                n = r[rB] & 0x3F; r[rA] = (r[rD] >> n) if n < 32 else 0
                if ins & 1: self.cmp0(r[rA])
            elif xo == 60: r[rA] = r[rD] & ~r[rB] & 0xFFFFFFFF
            elif xo in (124, 28, 316, 476, 412, 284):
                x, y = r[rD], r[rB]
                v = {124: ~(x | y), 28: x & y, 316: x ^ y, 476: ~(x & y), 412: x | ~y, 284: ~(x ^ y)}[xo] & 0xFFFFFFFF
                r[rA] = v
                if ins & 1: self.cmp0(v)
            elif xo == 922:
                v = r[rD] & 0xFFFF; r[rA] = (v - 0x10000 if v & 0x8000 else v) & 0xFFFFFFFF
                if ins & 1: self.cmp0(r[rA])
            elif xo == 824:
                sh = rB; v = r[rD] - (1 << 32) if r[rD] & 0x80000000 else r[rD]
                self.ca = 1 if v < 0 and (r[rD] & ((1 << sh) - 1)) else 0
                r[rA] = (v >> sh) & 0xFFFFFFFF
                if ins & 1: self.cmp0(r[rA])
            elif xo == 792:
                sh = r[rB] & 0x3F; v = r[rD] - (1 << 32) if r[rD] & 0x80000000 else r[rD]
                r[rA] = (v >> min(sh, 31)) & 0xFFFFFFFF
                if ins & 1: self.cmp0(r[rA])
            elif xo == 954:
                v = r[rD] & 0xFF; r[rA] = (v - 256 if v & 0x80 else v) & 0xFFFFFFFF
                if ins & 1: self.cmp0(r[rA])
            elif xo == 0:
                a = r[rA]; b = r[rB]
                a = a - (1 << 32) if a & 0x80000000 else a; b = b - (1 << 32) if b & 0x80000000 else b
                self.setcr(rD >> 2, a < b, a > b, a == b)
            elif xo == 19: r[rD] = self.cr & 0xFFFFFFFF                      # mfcr
            elif xo == 144:                                                     # mtcrf
                fxm = (ins >> 12) & 0xFF; crm = 0
                for i in range(8):
                    if fxm & (0x80 >> i): crm |= 0xF << (28 - 4 * i)
                self.cr = (self.cr & ~crm) | (r[rD] & crm)
            elif xo == 151: m.w32(((r[rA] if rA else 0) + r[rB]) & 0xFFFFFFFF, r[rD])   # stwx
            elif xo == 23: r[rD] = m.r32(((r[rA] if rA else 0) + r[rB]) & 0xFFFFFFFF)   # lwzx
            elif xo == 279: r[rD] = m.r16(((r[rA] if rA else 0) + r[rB]) & 0xFFFFFFFF)   # lhzx
            elif xo == 407: m.w16(((r[rA] if rA else 0) + r[rB]) & 0xFFFFFFFF, r[rD] & 0xFFFF)   # sthx
            elif xo == 215: m.w8(((r[rA] if rA else 0) + r[rB]) & 0xFFFFFFFF, r[rD] & 0xFF)   # stbx
            elif xo == 87: r[rD] = m.r8(((r[rA] if rA else 0) + r[rB]) & 0xFFFFFFFF)   # lbzx
            elif xo == 55: a = (r[rA] + r[rB]) & 0xFFFFFFFF; r[rD] = m.r32(a); r[rA] = a
            elif xo == 311: a = (r[rA] + r[rB]) & 0xFFFFFFFF; r[rD] = m.r16(a); r[rA] = a
            elif xo == 918:
                a = ((r[rA] if rA else 0) + r[rB]) & 0xFFFFFFFF; v = r[rD] & 0xFFFF
                m.w8(a, v); m.w8(a + 1, v >> 8)
            elif xo == 467 and ((ins >> 11) & 0x3FF) == 0x120: self.ctr = r[rD]
            elif xo == 32: self.setcr(rD >> 2, r[rA] < r[rB], r[rA] > r[rB], r[rA] == r[rB])
            elif xo == 339 and ((ins >> 11) & 0x3FF) == 0x100: r[rD] = self.lr
            elif xo == 467 and ((ins >> 11) & 0x3FF) == 0x100: self.lr = r[rD]
            elif xo == 83: r[rD] = self.msr
            elif xo == 146: self.msr = r[rD]
            else: raise Exception("op31 xo %d at %08x" % (xo, pc))
        elif op == 32: r[rD] = m.r32(ea())
        elif op == 33: a = ea(); r[rD] = m.r32(a); r[rA] = a
        elif op == 35: a = ea(); r[rD] = m.r8(a); r[rA] = a
        elif op == 39: a = ea(); m.w8(a, r[rD]); r[rA] = a
        elif op == 48: self.f[rD] = struct.unpack('>f', struct.pack('>I', m.r32(ea())))[0]
        elif op == 50: a = ea(); self.f[rD] = struct.unpack('>d', struct.pack('>II', m.r32(a), m.r32(a + 4)))[0]
        elif op == 52: m.w32(ea(), struct.unpack('>I', struct.pack('>f', f32(self.f[rD])))[0])
        elif op == 59:
            xo = (ins >> 1) & 31; rC = (ins >> 6) & 31; F = self.f
            if xo == 25: F[rD] = f32(F[rA] * F[rC])
            elif xo == 29: F[rD] = f32(F[rA] * F[rC] + F[rB])
            elif xo == 21: F[rD] = f32(F[rA] + F[rB])
            elif xo == 20: F[rD] = f32(F[rA] - F[rB])
            else: raise Exception("op59 xo %d at %08x" % (xo, pc))
        elif op == 63:
            xo10 = (ins >> 1) & 0x3FF; xo5 = (ins >> 1) & 31; F = self.f
            if xo10 == 0:
                a, b = F[rA], F[rB]; self.setcr(rD >> 2, a < b, a > b, a == b)
            elif xo10 == 12: F[rD] = f32(F[rB])
            elif xo10 == 72: F[rD] = F[rB]
            elif xo10 == 40: F[rD] = -F[rB]
            elif xo5 == 20: F[rD] = F[rA] - F[rB]
            elif xo5 == 21: F[rD] = F[rA] + F[rB]
            else: raise Exception("op63 xo %d at %08x" % (xo10, pc))
        elif op == 34: r[rD] = m.r8(ea())
        elif op == 40: r[rD] = m.r16(ea())
        elif op in (33, 35, 41):                       # lwzu, lbzu, lhzu
            a = ea(); r[rD] = m.r32(a) if op == 33 else m.r8(a) if op == 35 else m.r16(a); r[rA] = a
        elif op in (36, 37, 38, 39, 44, 45):
            a = ea()
            if (a & 0xFFFFFF00) == 0xCD000000: self.mmio_writes.append((a, r[rD], self.msr))
            if op in (38, 39): m.w8(a, r[rD])
            elif op in (44, 45): m.w16(a, r[rD])
            else: m.w32(a, r[rD])
            if op in (37, 39, 45): r[rA] = a          # stwu, stbu, sthu
        elif op == 46:
            a = ea()
            for i in range(rD, 32): r[i] = m.r32(a); a += 4
        elif op == 47:
            a = ea()
            for i in range(rD, 32): m.w32(a, r[i]); a += 4
        else: raise Exception("unknown op %d (%08x) at %08x" % (op, ins, pc))
        self.pc = npc
