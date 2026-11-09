/*
 * Wii Menu 4.3U (v513) Priiloader hack - PS3/PS4 controller as a Wii Menu pointer
 * Version 2: PS3 (DualShock 3) and PS4 (DualShock 4, CUH-ZCT1 and CUH-ZCT2).
 *
 * A wired PS3 or PS4 controller in one of the Wii's USB ports becomes a Wii
 * Remote in the Wii Menu (if both are plugged in, the PS3 one is used):
 *   left stick = pointer        Cross = A        Circle = B
 *   PS or Start/Options = HOME  L1 = -   R1 = +  Square = 1   Triangle = 2
 *   D-pad = Wii Remote D-pad    Select/Share = -
 * The PS4 light bar is set to red.
 *
 * USB: through /dev/usb/oh0, the interface Nintendo's own USB library in the
 * menu uses. Stage 1 found the setup this needs: SET_CONFIGURATION 1 (this
 * interface doesn't do it by itself), then GET_REPORT 0xF2 switches the
 * controller on. v2: after coming back from an emulator, the controller only
 * reported its PS button until PS was pressed, so setup now also sends what
 * Linux (GET_REPORT 0xF5) and ScpToolkit (SET_REPORT feature 0xF4 = 42 0C 00 00,
 * "enable") send. v2c: always SET_CONFIGURATION (2b skipped it when the
 * controller said it was configured, and after a Virtual Console game it then
 * ignored everything), and if no real report arrives within 2 s of setup,
 * close the controller and set it up again. v2d: after a Virtual Console game
 * the controller powered itself off ~10 s after returning (no live USB link),
 * so right after opening it, send IOS's "resume device" (ioctl 6 on the
 * device handle, see wiibrew /dev/usb/oh0) in case it was left suspended. Buttons and sticks are read with GET_REPORT input 1,
 * started in the background (IOS_IoctlvAsync) every frame and picked up the
 * next frame, so the menu never waits for USB.
 *
 * Wii Remote: same method as the GameCube controller hack for this menu
 * (github.com/maxwelmota/wiimenu-gcn-hack-enhanced, after dg4l): a fake
 * ipl::controller::Revolution object with its own KPADStatus goes into the
 * first free slot of the controller manager after the manager's own read, so
 * a real Wii Remote keeps its slot. Pointer speed and limits are the menu's
 * own Classic Controller pointer values (0.05 per frame, +-1.8, +-1.2).
 *
 * v2e found that when the controller is plugged in after IOS started (at the
 * menu, or late after an Arcade / Master System VC game), /dev/usb/oh0 says
 * "already in use" (-2): something inside IOS grabs it the moment it appears
 * (2g: IOS80 has no /dev/usb/hid; the menu's own code, per the wii-ipl
 * decompilation, never opens USB devices, so the likely grabber is IOS's USB
 * keyboard service).
 *
 * Stage 3a: race it. An insertion hook (/dev/usb/oh0 ioctlv 30,
 * DEVINSERTHOOKID, VID/PID 054C:0268, "new devices only") is kept waiting
 * from the menu's first frame. When IOS answers it, the open is sent straight
 * from that answer's callback (IOS_OpenAsync, the same way the menu's own
 * keyboard library re-sends requests from its callbacks), so the controller
 * is grabbed within microseconds. Setup still waits until 2 s into the menu.
 * If ioctlv 30 isn't there, the older ioctlv 27 hook is used instead.
 *
 * Disc-slot light: glows for ~1 s when the controller starts answering, and
 * is otherwise left alone (so the Wii's own new-message glow still works).
 * If the controller is lost after some Arcade / Master System VC games
 * (grabbed before the menu starts), unplug it and plug it back in.
 *
 * PS4 (stage 4, tests 1-8 on a real Wii): a wired DualShock 4 is opened as
 * /dev/usb/oh0/54c/9cc (CUH-ZCT2) or /54c/5c4 (CUH-ZCT1). Setup is
 * GET/SET_CONFIGURATION and reading the configuration descriptor for the HID
 * interface's endpoints (interface 3; 0-2 are audio). It then sends report 0x01
 * by itself; that is read from the interrupt IN endpoint (oh0 ioctlv 2; it
 * doesn't answer GET_REPORT) and converted to the PS3 layout (ds4report).
 * Two things the Wii needed (tests 4-7): the endpoint and length inputs must
 * each sit on their own 32-byte line (sharing one with the vectors let only the
 * first read after setup work, then IOS answered -1), and the vectors are set
 * again before every request. Light bar: output report 0x05 to the interrupt
 * OUT endpoint. Each controller ID (PS3, ZCT2, ZCT1) has its own plug-in hook,
 * so a PS4 controller can be plugged in at the menu too.
 * Build with CFLAGS=-DDIAG for the disc-slot blink codes (test build).
 *
 * Code and data live in 0x80001800-0x80003000, which the Wii's OS memory map
 * leaves unused (exception vectors end at 0x1800, OS globals start at 0x3000).
 * Hooked at the 4 getControllerManager()->read() calls in the menu's main
 * loops (same hook sites as the GameCube controller hack).
 */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef signed char s8;
typedef int s32;
typedef float f32;

typedef struct { void *base; u32 length; } IOVec;
typedef s32 (*IOSCallback)(s32 result, void *arg);

/* Wii Menu 4.3U functions (addresses in ps3menu.ld, from the wii-ipl decompilation's symbol map) */
s32  IOS_Open(const char *path, u32 mode);
s32  IOS_OpenAsync(const char *path, u32 mode, IOSCallback cb, void *arg);
s32  IOS_CloseAsync(s32 fd, IOSCallback cb, void *arg);
s32  IOS_Close(s32 fd);
s32  IOS_Ioctlv(s32 fd, s32 cmd, u32 in, u32 io, IOVec *vec);
s32  IOS_Ioctl(s32 fd, s32 cmd, void *in, u32 inLen, void *out, u32 outLen);
s32  IOS_IoctlAsync(s32 fd, s32 cmd, void *in, u32 inLen, void *out, u32 outLen, IOSCallback cb, void *arg);
void DCFlushRange(void *p, u32 len);
void DCInvalidateRange(void *p, u32 len);
s32  IOS_IoctlvAsync(s32 fd, s32 cmd, u32 in, u32 io, IOVec *vec, IOSCallback cb, void *arg);
void MgrRead(void *mgr);              /* ipl::controller::Manager::read */
void RevoRead(void *revo);            /* ipl::controller::Revolution::read */
#define manager    (*(void * volatile *)0x81089070)   /* System::smArg.controllerManager */
#define REVO_VTABLE 0x816347F4                         /* __vt__Q33ipl10controller10Revolution */

#define GPIOB_OUT  (*(volatile u32 *)0xCD0000C0)
#define SLOT_LED   0x20

#define LE16(x) ((u16)((((x) & 0xFF) << 8) | (((x) >> 8) & 0xFF)))

/* ---- KPADStatus (0x84 bytes) and the menu's controller object (0x24 bytes) ---- */
typedef struct {
	u32 hold, trig, release;     /* 0x00 */
	f32 acc[3], acc_value, acc_speed;
	f32 posx, posy;              /* 0x20 */
	f32 vec[2], speed;
	f32 horizonx, horizony;      /* 0x34 */
	f32 hori_vec[2], hori_speed, dist, dist_vec, dist_speed, acc_vertical[2];
	u8  dev_type;                /* 0x5C */
	s8  wpad_err;                /* 0x5D */
	s8  dpd_valid_fg;            /* 0x5E */
	u8  data_format;
	u8  ex_status[0x24];         /* 0x60 */
} KPAD;

typedef struct {
	u32 vtable;
	u8  mButton, p0[3];
	u32 unk08, lastRumbleTime;
	s32 rumbleType;
	u32 chan, type;
	u8  unk1C, unk1D, unk1E, p1;
	KPAD *kpad;                  /* 0x20 */
} Revo;

_Static_assert(sizeof(KPAD) == 0x84, "KPADStatus size");
_Static_assert(__builtin_offsetof(KPAD, dev_type) == 0x5C, "KPADStatus layout");
_Static_assert(__builtin_offsetof(Revo, kpad) == 0x20, "controller layout");

/* ---- USB buffers: everything IOS touches on its own 32-byte cache lines ---- */
/* an insertion hook: vectors, inputs and output each on their own 32-byte line */
typedef struct {
	IOVec v[4];                   /* +0x00 */
	struct {                      /* +0x20: inputs (big-endian, like libogc's "hh") */
		u16 vid, pid;
		u8  newOnly, pad[27];
	} hk;
	u32 id[8];                    /* +0x40: output (IOS writes it) */
} Hook;

typedef struct {
	IOVec vec[8];                 /* 0x00: 64 */
	u8  reqType, req;             /* 0x40: the control message's small inputs */
	u16 value, index, length;     /*       (little-endian) */
	u8  zero;
	char path[23];                /* 0x49 */
	u8  in[64];                   /* 0x60: reports read */
	u8  led[32];                  /* 0xA0: LED report */
	u8  enable[32];               /* 0xC0: "enable" feature report */
	char rootPath[32];            /* 0xE0 */
	Hook hook0;                   /* 0x100: plug-in hook for the PS3 controller */
	IOVec ivec[3];                /* 0x160: interrupt read (PS4): endpoint, length, data (U.in) - set before each read */
	u8  p3[8];
	char path4[2][32];            /* 0x180: PS4 controllers: newer (CUH-ZCT2), original (CUH-ZCT1) */
	u8  ep, p4[31];               /* 0x1C0: endpoint (own cache line, like libogc's separate buffers) */
	u16 ilen, p5[15];             /* 0x1E0: 64 (big-endian, like libogc's "bh:d") */
	Hook hook12[2];               /* 0x200: plug-in hooks for the PS4 controllers (ZCT2, ZCT1) */
	u8  bar[32];                  /* 0x2C0: PS4 output report 0x05: light bar colour */
#ifdef DIAG
	u8  desc[64];                 /* test build: only the start (to check the controller still answers); 0x84 assumed */
#else
	u8  desc[256];                /* 0x2E0: PS4 configuration descriptor (to find its endpoints) */
#endif
} Usb;

__attribute__((section(".usbdata"), aligned(32))) Usb U = {
	.vec = {
		{ &U.reqType, 1 }, { &U.req, 1 }, { &U.value, 2 },
		{ &U.index, 2 }, { &U.length, 2 }, { &U.zero, 1 },
	},
	.path = "/dev/usb/oh0/54c/268",   /* Sony, DualShock 3 / Sixaxis */
	.led = {                          /* player 1 LED: the report the emulator driver sends */
		0x52, 0x01, 0x00, 0x00, 0x00, 0xff, 0x80, 0x00, 0x00, 0x02,
		0xff, 0x27, 0x10, 0x00, 0x32, 0xff, 0x27, 0x10, 0x00, 0x32,
		0xff, 0x27, 0x10, 0x00, 0x32, 0xff, 0x27, 0x10, 0x00, 0x32,
	},
	.enable = { 0x42, 0x0C, 0x00, 0x00 },
	.rootPath = "/dev/usb/oh0",
	.hook0 = { .hk = { 0x054C, 0x0268, 1 } },
	.hook12 = { { .hk = { 0x054C, 0x09CC, 1 } }, { .hk = { 0x054C, 0x05C4, 1 } } },
	.bar = { 0x05, 0x07, 0x00, 0x00,      /* report 0x05; set rumble, light bar, flash */
	         0x00, 0x00,                  /* rumble off */
	         0xFF, 0x00, 0x00,            /* light bar: red */
	         0x00, 0x00 },                /* no flashing */
	.path4 = { "/dev/usb/oh0/54c/9cc", "/dev/usb/oh0/54c/5c4" },
};
_Static_assert(__builtin_offsetof(Usb, hook0) == 0x100 && sizeof(Hook) == 0x60, "hook layout");
_Static_assert(__builtin_offsetof(Usb, path4) % 32 == 0 && __builtin_offsetof(Usb, hook12) == 0x200 &&
               __builtin_offsetof(Usb, bar) == 0x2C0 && sizeof(Usb) == 0x2E0 + sizeof(U.desc), "PS4 layout");

/* control messages, as {typeReq, valueLE, length, buffer offset in U, indexLE} */
enum { STEP_GETCONF, STEP_SETCONF, STEP_ON, STEP_ON2, STEP_ENABLE, STEP_LED, STEP_READ, STEP_CFGDESC };
static const u16 steps[8][5] = {
	{ 0x8008, 0,            1,  0x60 },   /* standard/device/in:  GET_CONFIGURATION */
	{ 0x0009, LE16(1),      0,  0x60 },   /* standard/device/out: SET_CONFIGURATION 1 */
	{ 0xA101, LE16(0x03F2), 17, 0x60 },   /* class/interface/in:  GET_REPORT feature 0xF2 (switch on) */
	{ 0xA101, LE16(0x03F5), 8,  0x60 },   /* class/interface/in:  GET_REPORT feature 0xF5 (Linux hid-sony) */
	{ 0x2109, LE16(0x03F4), 4,  0xC0 },   /* class/interface/out: SET_REPORT feature 0xF4 42 0C 00 00 (ScpToolkit "enable") */
	{ 0x2109, LE16(0x0201), 32, 0xA0 },   /* class/interface/out: SET_REPORT output 1 (LED) */
	{ 0xA101, LE16(0x0101), 53, 0x60 },   /* class/interface/in:  GET_REPORT input 1 (buttons, sticks) */
	{ 0x8006, LE16(0x0200), sizeof(U.desc), 0x2E0 }, /* standard/device/in:  GET_DESCRIPTOR configuration (PS4) */
};

#define NO_READ (-0x7FFF)                 /* S.result right after setup: no read yet */

/* ---- everything else (never touched by IOS) ---- */
typedef struct {
	KPAD kpad;
	Revo revo;
	f32 posX, posY;
	u32 prevBtn;
	u32 frame;
	s32 fd;                       /* 0 = not open, else IOS fd + 1 */
	u32 nextTry;
	u32 ledAt;                    /* frame of the LED resend, 0 = done */
	u32 failCode;                 /* setup step that failed + 2, 0 = none */
	u32 lightUntil;               /* slot light on until this frame */
	u32 errors;                   /* reads failed in a row */
	volatile u32 busy;            /* a background read is in flight */
	volatile s32 result;          /* its result (bytes read, or an IOS error) */
	u32 waitFrames;               /* frames the read has been in flight */
	u32 haveInput;                /* the controller has answered */
	u8  report[12];               /* the last report's first bytes */
	u32 configWas;                /* the configuration the controller was in when opened */
	u32 goodAt;                   /* frame of the last real report (or of the setup) */
	u32 status;                   /* slot-light status while not working: 1 = can't open, 2 = silent */
	u32 detail;                   /* second flash group for status 3 */
	s32 rootFd;                   /* /dev/usb/oh0 itself: 0 = not yet, -1 = failed, else fd + 1 */
	u32 hookCmd[3];               /* per hook (0 PS3, 1 PS4 ZCT2, 2 PS4 ZCT1): 30 (DEVINSERTHOOKID) or 27 (DEVINSERTHOOK) */
	u32 hookFails[3];             /* the hook failed this many times in a row */
	u32 hookAt[3];                /* frame to (re)arm the hook */
	u32 hookArmed;                /* bit per hook: it is (or was last) really waiting */
	volatile u32 hookBusy[3];     /* the hook is waiting */
	volatile s32 hookResult[3];   /* 0x7FFFFFFF = nothing new */
	volatile u32 fired;           /* a hook has fired at least once */
	volatile u32 asyncIdx;        /* which controller the instant open is for */
	volatile s32 asyncOpen;       /* instant open: 0x7FFFFFFF none, 0x7FFFFFFE in flight, else its result */
	s32 hookOpen;                 /* result of the last instant open */
	u32 needSetup;                /* opened early: set it up at 2 s */
	u32 lightOn;                  /* 0 = not ours, 1/2 = on, and it was off/on before */
	u32 kind;                     /* the open controller: 0 = PS3, 1 = PS4 */
	u32 gen;                      /* read generation: answers to reads from before a close are ignored */
	u32 ep;                       /* the PS4 input endpoint (U.ep is set from this before each read) */
	u32 epOut;                    /* its output endpoint (light bar) */
#ifdef DIAG
	u32 dstart;                   /* frame the blink sequence (re)started */
	u32 shown[2];                 /* the numbers being blinked (frozen at the start of each repeat) */
	u32 diagLed;                  /* blink codes: 0 = not started, 1/2 = running, light was off/on before, 3 = done */
#endif
} State;

__attribute__((section(".state"), aligned(32))) State S;

static void prepare(u32 step)
{
	const u16 *s = steps[step];
	U.reqType = (u8)(s[0] >> 8);
	U.req = (u8)s[0];
	U.value = s[1];
	U.index = s[4];
	U.length = LE16(s[2]);
	U.vec[6].base = (u8 *)&U + s[3];
	U.vec[6].length = s[2];
}

/* blocking control message through /dev/usb/oh0 (setup only) */
static s32 ctrl(s32 fd, u32 step)
{
	prepare(step);
	return IOS_Ioctlv(fd, 0 /* USB_IOCTLV_CTRLMSG */, 6, 1, U.vec);   /* flushes and converts for us */
}

static s32 sendStep(u32 step)
{
	return ctrl(S.fd - 1, step);
}

/* runs in the IPC interrupt when a background read finishes: just record it */
static s32 readDone(s32 result, void *arg)
{
	if ((u32)arg != S.gen)
		return 0;                     /* a read from before a close: ignore */
	S.result = result;
	S.busy = 0;
	return 0;
}

static Hook *hookOf(u32 i)
{
	return i ? &U.hook12[i - 1] : &U.hook0;
}

static const char *pathOf(u32 i)
{
	return i ? U.path4[i - 1] : U.path;
}

/* ---- instant open on plug-in: these run in the IPC interrupt ---- */
static s32 openDone(s32 result, void *arg)
{
	(void)arg;
	S.asyncOpen = result;
	return 0;
}

static s32 closeDone(s32 result, void *arg)
{
	(void)result; (void)arg;
	if (IOS_OpenAsync(pathOf(S.asyncIdx), 0, openDone, 0) < 0)
		S.asyncOpen = -99;
	return 0;
}

static s32 hookDone(s32 result, void *arg)
{
	u32 i = (u32)arg;
	S.hookResult[i] = result;
	S.hookBusy[i] = 0;
	if (result < 0)
		return 0;
	S.fired = 1;
	if (S.fd && S.haveInput && S.errors == 0)
		return 0;                     /* already have a working one (a second controller?) */
	if (S.asyncOpen == 0x7FFFFFFE)
		return 0;                     /* already opening one that was just plugged in */
	S.asyncOpen = 0x7FFFFFFE;
	S.asyncIdx = i;
	if (S.fd) {                           /* a dead handle from before it was unplugged: drop it first */
		s32 old = S.fd - 1;
		S.gen++;
		S.fd = 0;
		S.haveInput = 0;
		if (IOS_CloseAsync(old, closeDone, 0) < 0)
			closeDone(0, 0);
	} else if (IOS_OpenAsync(pathOf(i), 0, openDone, 0) < 0) {
		S.asyncOpen = -99;
	}
	return 0;
}

static void armHook(u32 i)
{
	Hook *h = hookOf(i);
	u32 c = S.hookCmd[i];
	S.hookResult[i] = 0x7FFFFFFF;
	S.hookBusy[i] = 1;
	h->v[0].base = &h->hk.vid;            /* (set every time: the menu's IOS_IoctlvAsync */
	h->v[0].length = 2;                   /*  leaves addresses converted, see the read below) */
	h->v[1].base = &h->hk.pid;
	h->v[1].length = 2;
	h->v[2].base = &h->hk.newOnly;
	h->v[2].length = 1;
	h->v[3].base = h->id;
	h->v[3].length = 4;
	if (IOS_IoctlvAsync(S.rootFd - 1, c, c == 30 ? 3 : 2, c == 30 ? 1 : 0, h->v, hookDone, (void *)i) < 0) {
		S.hookBusy[i] = 0;
		S.hookResult[i] = -1;
	} else {
		S.hookArmed |= 1u << i;
	}
}

static void slotLed(int on)
{
	u32 msr, v;
	__asm__ volatile ("mfmsr %0" : "=r"(msr));
	__asm__ volatile ("mtmsr %0" : : "r"(msr & ~0x8000u));   /* no interrupts during read-modify-write */
	v = GPIOB_OUT;
	GPIOB_OUT = on ? (v | SLOT_LED) : (v & ~SLOT_LED);
	__asm__ volatile ("mtmsr %0" : : "r"(msr));
}


#ifndef DIAG
/* PS4: the HID interface's interrupt IN endpoint, from the configuration descriptor */
static u32 findEp(void)
{
	u32 i = 0, hid = 0, total = U.desc[2] | (U.desc[3] << 8);
	if (total > sizeof(U.desc))
		total = sizeof(U.desc);
	while (i + 4 <= total && U.desc[i] >= 2) {
		const u8 *d = &U.desc[i];
		if (d[1] == 4)
			hid = d[5] == 3;          /* interface: class HID? */
		else if (d[1] == 5 && hid && (d[3] & 3) == 3) {   /* endpoint: interrupt */
			if (d[2] & 0x80)
				S.ep = d[2];      /* IN */
			else
				S.epOut = d[2];   /* OUT */
		}
		i += d[0];
	}
	return 0;
}
#endif

/* PS4: set the light bar (output report 0x05 to its interrupt OUT endpoint).
   (Left out of the DIAG test build, which is otherwise too big.) */
#ifdef DIAG
#define lightBar() ((void)0)
#else
static void lightBar(void)
{
	U.ivec[0].base = &U.ep;
	U.ivec[0].length = 1;
	U.ivec[1].base = &U.ilen;
	U.ivec[1].length = 2;
	U.ivec[2].base = U.bar;
	U.ivec[2].length = 32;
	U.ep = S.epOut;
	U.ilen = 32;
	IOS_Ioctlv(S.fd - 1, 2 /* USBV0_IOCTLV_INTRMSG */, 2, 1, U.ivec);
}
#endif

/* the controller was just opened (S.fd set): set it up */
static void setupPad(u32 f)
{
	u32 code = 0;
	IOS_Ioctl(S.fd - 1, 6 /* USBV0_IOCTL_RESUMEDEV */, 0, 0, 0, 0);   /* in case it was left suspended */
	if (sendStep(STEP_GETCONF) < 0)
		code = 2;
	S.configWas = U.in[0];
	if (sendStep(STEP_SETCONF) < 0 && code == 0)   /* always, even if it says it's configured */
		code = 3;
	S.ledAt = 0;
	if (S.kind == 0) {                    /* PS3 only: a PS4 controller sends its reports by itself */
		if (sendStep(STEP_ON) < 0 && code == 0)
			code = 4;
		sendStep(STEP_ON2);           /* extra wake-ups: some controllers refuse these, that's fine */
		sendStep(STEP_ENABLE);
		if (sendStep(STEP_LED) < 0 && code == 0)
			code = 5;
		S.ledAt = f + 60;             /* repeat the LED once: a freshly powered controller can miss it */
	} else {                              /* PS4: find its endpoints (it then sends its reports by itself) */
		S.ep = 0x84;                  /* the usual PS4 endpoints, if the descriptor doesn't say */
		S.epOut = 0x03;
#ifndef DIAG
		U.desc[1] = 0;
		if (sendStep(STEP_CFGDESC) >= 0 && U.desc[1] == 2)
			findEp();
#endif
		lightBar();
		S.ledAt = f + 60;             /* and once more a second later, like the PS3 LED */
	}
	S.failCode = code;
	S.status = 2;                         /* "silent" until it answers */
	S.goodAt = f;                         /* no real report within 2 s of this: set it up again */
	S.errors = 0;
	S.haveInput = 0;
	S.busy = 0;
	S.result = NO_READ;
}

static void openPad(u32 f)
{
	s32 fd = 0, inUse = 0;
	u32 k;
	S.nextTry = f + 120;                  /* (plug-ins are caught by the hooks; this is the backup) */
	for (k = 0; k < 3; k++) {             /* PS3, then PS4 (CUH-ZCT2), then PS4 (CUH-ZCT1) */
		fd = IOS_Open(pathOf(k), 0);
		if (fd >= 0) {
			S.fd = fd + 1;
			S.kind = k != 0;
			setupPad(f);
			return;
		}
		if (fd == -2)
			inUse = 1;
	}
	if (!inUse) {                         /* none there (or some other error) */
		S.status = 1;
		return;
	}
	S.status = 3;                         /* in use by something else in IOS */
}

static void closePad(u32 f)
{
	S.gen++;                              /* a read still in flight is now stale */
	IOS_Close(S.fd - 1);
	S.fd = 0;
	S.haveInput = 0;
	S.nextTry = f + 30;                   /* open it again in half a second */
}

/* PS4 report 0x01 (from the interrupt endpoint) -> the PS3 report layout the
   rest of the code reads: [2] Select/Start/D-pad, [3] L1/R1/shapes, [4] PS,
   [6]/[7] left stick. PS4: [1]/[2] left stick, [5] D-pad (hat) + shapes,
   [6] L1, R1, Share, Options, [7] PS. Share = Select, Options = Start. */
static const u8 hatBits[8] = { 0x10, 0x30, 0x20, 0x60, 0x40, 0xC0, 0x80, 0x90 };   /* N NE E SE S SW W NW */

static void ds4report(void)
{
	u8 b5 = U.in[5], b6 = U.in[6], b2 = 0, b3 = 0;
	if ((b5 & 0x0F) < 8)
		b2 = hatBits[b5 & 0x0F];
	if (b6 & 0x10) b2 |= 0x01;            /* Share    -> Select */
	if (b6 & 0x20) b2 |= 0x08;            /* Options  -> Start */
	if (b5 & 0x10) b3 |= 0x80;            /* Square */
	if (b5 & 0x20) b3 |= 0x40;            /* Cross */
	if (b5 & 0x40) b3 |= 0x20;            /* Circle */
	if (b5 & 0x80) b3 |= 0x10;            /* Triangle */
	if (b6 & 0x01) b3 |= 0x04;            /* L1 */
	if (b6 & 0x02) b3 |= 0x08;            /* R1 */
	S.report[2] = b2;
	S.report[3] = b3;
	S.report[4] = U.in[7] & 0x01;         /* PS */
	S.report[6] = U.in[1];
	S.report[7] = U.in[2];
}

static void usb(u32 f)
{
	/* the plug-in hook: from the first frame on */
	u32 i;
	if (S.rootFd == 0) {
		s32 r = IOS_Open(U.rootPath, 0);
		S.rootFd = r >= 0 ? r + 1 : -1;
		for (i = 0; i < 3; i++) {
			S.hookCmd[i] = 30;
			S.hookResult[i] = 0x7FFFFFFF;
		}
		S.asyncOpen = 0x7FFFFFFF;
	}
	for (i = 0; i < 3; i++) {             /* one hook per controller ID */
		if (!S.hookBusy[i] && S.hookResult[i] != 0x7FFFFFFF) {   /* it answered */
			if (S.hookResult[i] < 0) {
				S.hookArmed &= ~(1u << i);   /* it never really waited */
				S.hookAt[i] = f + 60;
				if (++S.hookFails[i] >= 3 && S.hookCmd[i] == 30) {
					S.hookCmd[i] = 27;   /* no ioctlv 30: the older hook */
					S.hookFails[i] = 0;
				}
			} else {
				S.hookFails[i] = 0;
				S.hookAt[i] = f + (S.hookCmd[i] == 30 ? 1 : 30);   /* (27 also answers at once if it's there) */
			}
			S.hookResult[i] = 0x7FFFFFFF;
		}
		if (S.rootFd > 0 && !S.hookBusy[i] && f >= S.hookAt[i] && S.hookFails[i] < 3)
			armHook(i);
	}

	/* the instant open finished */
	if (S.asyncOpen != 0x7FFFFFFF && S.asyncOpen != 0x7FFFFFFE) {
		s32 r = S.asyncOpen;
		S.asyncOpen = 0x7FFFFFFF;
		S.hookOpen = r;
		if (r >= 0 && S.fd == 0) {
			S.fd = r + 1;
			S.kind = S.asyncIdx != 0; /* which hook fired: PS3 or PS4 */
			S.needSetup = 1;
		} else if (r >= 0) {
			IOS_Close(r);             /* (can't happen: we had none open) */
		}
	}
	if (S.asyncOpen == 0x7FFFFFFE)
		return;                       /* wait for it */
	if (S.fd && S.needSetup) {
		if (f >= 120) {
			S.needSetup = 0;
			setupPad(f);
		}
		return;
	}

	if (S.fd == 0) {
		if (f >= S.nextTry && f >= 120)   /* first look ~2 s after the menu starts, like test 2 */
			openPad(f);
		return;
	}
	if (S.busy) {
		/* a PS4 read that never comes back: start over */
		if (S.kind && ++S.waitFrames > 120) {
			S.busy = 0;
			closePad(f);
			return;
		}
		/* a read that never comes back: give up on the controller (needs a restart to come back) */
		if (!S.kind && ++S.waitFrames > 300) {
			S.haveInput = 0;
			S.fd = 0;
			S.nextTry = 0xFFFFFFFF;
		}
		return;
	}
	/* the last background read is done */
	if (S.result >= 10 && (S.kind == 0 || U.in[0] == 0x01)) {
		u32 i;
		if (S.kind) {
			ds4report();
		}
		else
			for (i = 0; i < 12; i++)
				S.report[i] = U.in[i];
		if (!S.haveInput)
			S.lightUntil = f + 60;     /* answering: slot light on for a second */
		S.haveInput = 1;
		S.errors = 0;
		S.goodAt = f;
		S.status = 0;
	} else {
		if (++S.errors >= 30 || f - S.goodAt > 120) {
			closePad(f);           /* unplugged, not answering, or only empty replies: start over */
			return;
		}
	}
	if (S.ledAt != 0 && f >= S.ledAt) {
		S.ledAt = 0;
		if (S.kind)
			lightBar();
		else
			sendStep(STEP_LED);
	}
	/* start the next read */
	S.busy = 1;
	S.waitFrames = 0;
	prepare(STEP_READ);
	/* PS4: an interrupt read. Its endpoint and length each sit on their own 32-byte
	   line (like libogc's separate buffers): when they shared a line with the
	   vectors, only the first read after setup ever worked and IOS answered every
	   later one with -1 (PS4 tests 1-7). The vectors are also set again every time,
	   since the menu's IOS_IoctlvAsync converts their addresses for IOS in place. */
	if (S.kind) {
		U.ivec[0].base = &U.ep;
		U.ivec[0].length = 1;
		U.ivec[1].base = &U.ilen;
		U.ivec[1].length = 2;
		U.ivec[2].base = U.in;
		U.ivec[2].length = 64;
		U.ep = S.ep;
		U.ilen = 64;
	}
	if ((S.kind ? IOS_IoctlvAsync(S.fd - 1, 2 /* USBV0_IOCTLV_INTRMSG */, 2, 1, U.ivec, readDone, (void *)S.gen)
	            : IOS_IoctlvAsync(S.fd - 1, 0, 6, 1, U.vec, readDone, (void *)S.gen)) < 0) {
		S.busy = 0;
		S.result = -9999;             /* couldn't even send it */
	}
}

/* stick axis 0..255 -> -1..1, with a deadzone */
static f32 axis(u8 raw)
{
	s32 v = (s32)raw - 128;
	if (v >= -12 && v <= 12)
		return 0.0f;
	return (f32)v * (1.0f / 128.0f);
}

static f32 clampf(f32 v, f32 lim)
{
	return v > lim ? lim : (v < -lim ? -lim : v);
}

/* PS3 report -> Wii Remote buttons (KPAD hold bits) */
static u32 buttons(void)
{
	u8 b2 = S.report[2], b3 = S.report[3], b4 = S.report[4];
	u32 w = 0;
	if (b2 & 0x10) w |= 0x0008;            /* D-up     -> up */
	if (b2 & 0x40) w |= 0x0004;            /* D-down   -> down */
	if (b2 & 0x80) w |= 0x0001;            /* D-left   -> left */
	if (b2 & 0x20) w |= 0x0002;            /* D-right  -> right */
	if (b3 & 0x40) w |= 0x0800;            /* Cross    -> A */
	if (b3 & 0x20) w |= 0x0400;            /* Circle   -> B */
	if (b3 & 0x80) w |= 0x0200;            /* Square   -> 1 */
	if (b3 & 0x10) w |= 0x0100;            /* Triangle -> 2 */
	if (b3 & 0x04) w |= 0x1000;            /* L1       -> - */
	if (b2 & 0x01) w |= 0x1000;            /* Select   -> - */
	if (b3 & 0x08) w |= 0x0010;            /* R1       -> + */
	if ((b2 & 0x08) || (b4 & 0x01)) w |= 0x8000;   /* Start, PS -> HOME */
	return w;
}

#ifdef DIAG
/* the blink sequence for these numbers at time t: 1 = light on, 0 = off, 2 = finished */
static u32 play(const u32 *n, u32 cnt, u32 t)
{
	u32 i, j;
	for (i = 0; i < cnt; i++) {
		u32 dg[5], nd = 0, v = n[i], p = 10000;
		while (p > 1 && v < p)
			p /= 10;
		for (; p; p /= 10)
			dg[nd++] = v / p % 10;
		if (v == 7777)                    /* "didn't happen": two long blinks */
			dg[0] = dg[1] = 0, nd = 2;
		for (j = 0; j < nd; j++) {
			u32 len = dg[j] ? dg[j] * 25 : 60;
			if (t < len)
				return dg[j] ? t % 25 < 12 : t < 45;
			t -= len;
			len = j + 1 < nd ? 50 : 150;
			if (t < len)
				return 0;
			t -= len;
		}
	}
	return t < 400 ? 0 : 2;
}
#endif

void ps3hook(void)
{
	u32 f = ++S.frame, i, btn;
	void **slots;
	KPAD *k = &S.kpad;

	usb(f);

	if (S.haveInput) {
		S.posX = clampf(S.posX + axis(S.report[6]) * 0.05f, 1.8f);
		S.posY = clampf(S.posY + axis(S.report[7]) * 0.05f, 1.2f);   /* PS sticks: down is positive, like the pointer */
		k->posx = S.posX;
		k->posy = S.posY;
		k->horizonx = 1.0f;          /* pointer upright */
		k->horizony = 0.0f;
		k->dpd_valid_fg = 1;
		k->wpad_err = 0;
		btn = buttons();
		k->hold = btn;
		k->trig = btn & ~S.prevBtn;
		k->release = S.prevBtn & ~btn;
		S.prevBtn = btn;
	} else {
		k->hold = k->trig = k->release = 0;
		k->wpad_err = -1;
		k->dpd_valid_fg = 0;
		S.prevBtn = 0;
	}

	/* the menu's own read; our fake Wii Remote steps out of its slot first, so a
	   newly connected real Wii Remote can take its own slot */
	slots = (void **)manager;
	if (slots && S.revo.chan < 4 && slots[S.revo.chan] == (void *)&S.revo)
		slots[S.revo.chan] = 0;
	if (slots)
		MgrRead(slots);

	slots = (void **)manager;
	if (S.haveInput && slots) {
		if (S.revo.vtable == 0) {
			S.revo.vtable = REVO_VTABLE;
			S.revo.rumbleType = -1;
			S.revo.type = 0;
			S.revo.kpad = k;
		}
		for (i = 0; i < 4; i++) {
			if (slots[i] == 0) {           /* first free slot: player 1, or 2 if a Wii Remote is player 1 */
				S.revo.chan = i;
				slots[i] = &S.revo;
				RevoRead(&S.revo);
				break;
			}
		}
	}

#ifdef DIAG
	/* test build: while no controller works, from 5 s to 2 min, the disc slot
	   blinks a code (a digit 1-9 is that many short blinks; long pause before
	   it repeats):
	     1 = no PS3/PS4 controller found
	     2 = found, but no buttons come through
	     3 then a 2nd number = found, but something in IOS is using it. The 2nd
	         number is about the plug-in hooks: 1 none could be set up, 2 set up
	         but never fired, 3 one fired but the controller was taken anyway,
	         4 one fired and something else went wrong.
	   The light goes back to how it was afterwards. */
	{
		u32 on = 0;
		if (f >= 300 && f < 7500 && !S.haveInput && S.status) {
			if (!S.diagLed || f == S.dstart) {    /* a new repeat: freeze the numbers for it */
				if (!S.diagLed)
					S.diagLed = 1 + ((GPIOB_OUT & SLOT_LED) != 0);
				S.dstart = f;
				S.shown[0] = S.status;
				S.shown[1] = !S.hookArmed ? 1 : !S.fired ? 2 : S.hookOpen == -2 ? 3 : 4;
			}
			on = play(S.shown, S.shown[0] == 3 ? 2 : 1, f - S.dstart);
			if (on == 2) {
				S.dstart = f + 1;             /* next frame starts a new repeat */
				on = 0;
			}
			slotLed(on);
		} else if (S.diagLed) {
			slotLed(S.diagLed == 2);
			S.diagLed = 0;
		}
	}
#endif

	/* disc-slot light: on for a second when the controller starts answering, then
	   back off once; never touched otherwise */
	if (S.lightUntil) {
		if (f < S.lightUntil) {
			if (!S.lightOn) {
				S.lightOn = 1 + ((GPIOB_OUT & SLOT_LED) != 0);   /* remember how it was */
				slotLed(1);
			}
		} else {
			if (S.lightOn)
				slotLed(S.lightOn == 2);   /* back to how it was */
			S.lightOn = 0;
			S.lightUntil = 0;
		}
	}
}
