"""
macddc.py — DDC/CI (VCP) access on macOS, Apple Silicon.

There is no /dev/i2c-* on macOS. The DDC I2C channel that rides on the
DisplayPort AUX link is only reachable through IOKit. On Apple Silicon the
(undocumented, but stable since Big Sur) entry points are:

    IOAVService IOAVServiceCreateWithService(CFAllocatorRef, io_service_t);
    IOReturn    IOAVServiceWriteI2C(IOAVService, uint32_t chipAddr,
                                    uint32_t dataAddr, void *buf, uint32_t len);
    IOReturn    IOAVServiceReadI2C (IOAVService, uint32_t chipAddr,
                                    uint32_t offset,   void *buf, uint32_t len);

They are exported from IOKit.framework, so plain ctypes is enough — no compiler,
no root, no entitlements. This is the same mechanism m1ddc / MonitorControl /
BetterDisplay use.

Intel Macs use a completely different path (IOFramebuffer + IOI2CSendRequest);
see the note at the bottom of this file.
"""

import ctypes
import platform
import time
from ctypes import POINTER, byref, c_bool, c_char_p, c_int, c_long, c_uint32, c_ulong, c_void_p

if platform.system() != "Darwin":
    raise ImportError("macddc only runs on macOS")

_IOKIT = "/System/Library/Frameworks/IOKit.framework/IOKit"
_CORE = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"

iokit = ctypes.CDLL(_IOKIT)
cf = ctypes.CDLL(_CORE)

KERN_SUCCESS = 0
kIOMainPortDefault = 0
kCFStringEncodingUTF8 = 0x08000100

# --- DDC/CI constants ------------------------------------------------------
DDC_CHIP_ADDR = 0x37   # 7-bit I2C slave address of the display's DDC/CI endpoint
DDC_DATA_ADDR = 0x51   # DDC/CI source address == the I2C "register"/offset we talk to
DDC_DEST_ADDR = 0x6E   # 8-bit write address; only used as the checksum seed here
DDC_MIN_GAP = 0.05     # MCCS says >=40ms between transactions; be generous

# ---------------------------------------------------------------------------
# CoreFoundation glue.  NOTE: restype MUST be set for anything returning a
# pointer, otherwise ctypes truncates it to 32 bit and you get garbage.
# ---------------------------------------------------------------------------
cf.CFStringCreateWithCString.restype = c_void_p
cf.CFStringCreateWithCString.argtypes = [c_void_p, c_char_p, c_uint32]
cf.CFStringGetCString.restype = c_bool
cf.CFStringGetCString.argtypes = [c_void_p, c_char_p, c_long, c_uint32]
cf.CFGetTypeID.restype = c_ulong
cf.CFGetTypeID.argtypes = [c_void_p]
cf.CFStringGetTypeID.restype = c_ulong
cf.CFRelease.argtypes = [c_void_p]

# ---------------------------------------------------------------------------
# IOKit glue
# ---------------------------------------------------------------------------
iokit.IOServiceMatching.restype = c_void_p
iokit.IOServiceMatching.argtypes = [c_char_p]
iokit.IOServiceGetMatchingServices.restype = c_int
iokit.IOServiceGetMatchingServices.argtypes = [c_uint32, c_void_p, POINTER(c_uint32)]
iokit.IOIteratorNext.restype = c_uint32
iokit.IOIteratorNext.argtypes = [c_uint32]
iokit.IOObjectRelease.argtypes = [c_uint32]
iokit.IORegistryEntryCreateCFProperty.restype = c_void_p
iokit.IORegistryEntryCreateCFProperty.argtypes = [c_uint32, c_void_p, c_void_p, c_uint32]

iokit.IOAVServiceCreateWithService.restype = c_void_p
iokit.IOAVServiceCreateWithService.argtypes = [c_void_p, c_uint32]
iokit.IOAVServiceWriteI2C.restype = c_int
iokit.IOAVServiceWriteI2C.argtypes = [c_void_p, c_uint32, c_uint32, c_void_p, c_uint32]
iokit.IOAVServiceReadI2C.restype = c_int
iokit.IOAVServiceReadI2C.argtypes = [c_void_p, c_uint32, c_uint32, c_void_p, c_uint32]


def _cfstr(s: str):
    return cf.CFStringCreateWithCString(None, s.encode(), kCFStringEncodingUTF8)


def _cfstr_to_py(ref):
    buf = ctypes.create_string_buffer(512)
    if not cf.CFStringGetCString(ref, buf, len(buf), kCFStringEncodingUTF8):
        return None
    return buf.value.decode(errors="replace")


def _prop_string(entry: int, key: str):
    k = _cfstr(key)
    try:
        ref = iokit.IORegistryEntryCreateCFProperty(entry, k, None, 0)
        if not ref:
            return None
        try:
            if cf.CFGetTypeID(ref) != cf.CFStringGetTypeID():
                return None
            return _cfstr_to_py(ref)
        finally:
            cf.CFRelease(ref)
    finally:
        cf.CFRelease(k)


def _matching_services(class_name: str):
    """Yield io_service_t for every IORegistry node of the given class."""
    matching = iokit.IOServiceMatching(class_name.encode())
    it = c_uint32(0)
    # IOServiceGetMatchingServices consumes the matching dict reference.
    if iokit.IOServiceGetMatchingServices(kIOMainPortDefault, matching, byref(it)) != KERN_SUCCESS:
        return
    try:
        while True:
            svc = iokit.IOIteratorNext(it)
            if not svc:
                break
            yield svc
    finally:
        iokit.IOObjectRelease(it)


def list_displays():
    """
    Return the io_service_t of every *external* DCPAVServiceProxy, in IORegistry
    order.  The index into this list is what we use as the 'device ID', mirroring
    ddcutil's -b <bus>.

    Caller owns the returned services and must IOObjectRelease() them.
    """
    found = []
    for svc in _matching_services("DCPAVServiceProxy"):
        if _prop_string(svc, "Location") == "External":
            found.append(svc)
        else:
            iokit.IOObjectRelease(svc)
    return found

class _StaleReply(Exception):
    pass

class MacDDCDevice:
    """ddcutil-equivalent handle for one external display."""

    def __init__(self, device_id: int = 0):
        services = list_displays()
        try:
            if not services:
                raise RuntimeError(
                    "No external DDC-capable display found. Note: the built-in HDMI "
                    "port of M1/entry-level M2 Macs does not expose DDC — use USB-C/DP."
                )
            if device_id >= len(services):
                raise RuntimeError(
                    "device ID %d out of range (%d external display(s) found)"
                    % (device_id, len(services))
                )
            self.av = iokit.IOAVServiceCreateWithService(None, services[device_id])
        finally:
            for s in services:
                iokit.IOObjectRelease(s)

        if not self.av:
            raise RuntimeError("IOAVServiceCreateWithService failed for device %d" % device_id)
        self.deviceID = device_id
        self._last = 0.0

    # -- low level ----------------------------------------------------------
    def _throttle(self):
        gap = time.monotonic() - self._last
        if gap < DDC_MIN_GAP:
            time.sleep(DDC_MIN_GAP - gap)

    @staticmethod
    def _checksum(payload: bytes) -> int:
        # DDC/CI: XOR of destination addr, source addr and every payload byte.
        chk = DDC_DEST_ADDR ^ DDC_DATA_ADDR
        for b in payload:
            chk ^= b
        return chk & 0xFF

    def _write_raw(self, payload: bytes):
        frame = bytes(payload) + bytes([self._checksum(payload)])
        buf = (ctypes.c_ubyte * len(frame)).from_buffer_copy(frame)
        self._throttle()
        rc = iokit.IOAVServiceWriteI2C(self.av, DDC_CHIP_ADDR, DDC_DATA_ADDR, buf, len(frame))
        self._last = time.monotonic()
        if rc != KERN_SUCCESS:
            raise OSError("IOAVServiceWriteI2C failed: 0x%08x" % (rc & 0xFFFFFFFF))

    def _read_raw(self, length: int = 12) -> bytes:
        buf = (ctypes.c_ubyte * length)()
        self._throttle()
        rc = iokit.IOAVServiceReadI2C(self.av, DDC_CHIP_ADDR, DDC_DATA_ADDR, buf, length)
        self._last = time.monotonic()
        if rc != KERN_SUCCESS:
            raise OSError("IOAVServiceReadI2C failed: 0x%08x" % (rc & 0xFFFFFFFF))
        return bytes(buf)

    # -- VCP ----------------------------------------------------------------
    def write(self, vcp_code: int, value: int, fire_and_forget: bool = False):
        """Set VCP feature (MCCS 'Set VCP Feature', opcode 0x03). 16-bit value."""
        payload = bytes([
            0x84,                      # 0x80 | length(4)
            0x03,                      # Set VCP Feature
            vcp_code & 0xFF,
            (value >> 8) & 0xFF,       # SH
            value & 0xFF,              # SL
        ])
        try:
            self._write_raw(payload)
        except OSError:
            # Switching the input away from this Mac kills the link mid-write.
            # That is expected and not an error for InputSelect / PBP swaps.
            if not fire_and_forget:
                raise

    def read(self, vcp_code: int, retries: int = 8):
        payload = bytes([0x82, 0x01, vcp_code & 0xFF])
        last_err = None
        for attempt in range(retries):
            try:
                self._write_raw(payload)
                time.sleep(0.06 + 0.02 * attempt)     # grow the settle each try
                r = self._read_raw(12)
                if r[4] != (vcp_code & 0xFF):
                    # stale/previous-transaction buffer — retry, don't fail
                    raise _StaleReply(r.hex())
                if r[3] != 0x00:
                    raise OSError("VCP 0x%02x rejected (result=0x%02x): %s"
                                % (vcp_code, r[3], r.hex()))
                maximum = (r[6] << 8) | r[7]
                current = (r[8] << 8) | r[9]
                return current, maximum
            except (_StaleReply, OSError) as e:
                last_err = e
                time.sleep(0.12)
        raise OSError("no fresh reply for VCP 0x%02x after %d tries (last: %s)"
                    % (vcp_code, retries, last_err))

    def set_verify(self, vcp_code: int, value: int, tol: int = 0,
                attempts: int = 5, readable: bool = True):
        """Write a VCP value and confirm it landed. Returns True on success.

        On Apple Silicon the DCP silently drops some writes (returns success but
        the panel never updates), so we write, settle, read back, and retry.
        For non-readable / link-dropping features (input select, PBP) pass
        readable=False — we can't verify, so we just fire twice with a gap.
        """
        if not readable:
            for _ in range(2):
                self.write(vcp_code, value, fire_and_forget=True)
                time.sleep(0.25)
            return None  # unverifiable

        for i in range(attempts):
            self.write(vcp_code, value)
            time.sleep(0.15)                       # let the panel apply it
            try:
                cur, _ = self.read(vcp_code)
            except OSError:
                continue
            if abs(cur - value) <= tol:
                return True
            time.sleep(0.1 * (i + 1))              # back off and retry
        return False

    def set_robust(self, vcp_code: int, value: int, tries: int = 3):
        for _ in range(tries):
            self.write(vcp_code, value, fire_and_forget=True)
            time.sleep(0.15)

    def open(self):      # API parity with monitorcontrol
        return self

    def close(self):
        if getattr(self, "av", None):
            cf.CFRelease(self.av)
            self.av = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


if __name__ == "__main__":
    import sys
    # usage: macddc.py <dev> getvcp <code>
    #        macddc.py <dev> setvcp <code> <value>
    dev, op = int(sys.argv[1]), sys.argv[2]
    d = MacDDCDevice(dev)
    if op == "getvcp":
        code = int(sys.argv[3], 16)
        cur, mx = d.read(code)
        print("VCP 0x%02x: current=0x%04x (%d)  max=0x%04x" % (code, cur, cur, mx))
    elif op == "setvcp":
        code, val = int(sys.argv[3], 16), int(sys.argv[4], 16)
        # features that tear down the link or don't read back
        unverifiable = code in (0x60, 0xe5, 0xe7, 0xe8, 0xe9)
        ok = d.set_verify(code, val, readable=not unverifiable)
        if ok is True:
            print("set VCP 0x%02x = 0x%04x (verified)" % (code, val))
        elif ok is False:
            sys.exit("set VCP 0x%02x = 0x%04x FAILED to stick after retries" % (code, val))
        else:
            print("set VCP 0x%02x = 0x%04x (sent, unverifiable)" % (code, val))
    else:
        sys.exit("usage: getvcp <code> | setvcp <code> <value>")


# ---------------------------------------------------------------------------
# Intel Macs
# ---------------------------------------------------------------------------
# IOAVService* does not exist there. The equivalent is:
#   io_service_t fb = CGDisplayIOServicePort(...) / IOFramebuffer matching
#   IOFBCopyI2CInterfaceForBus(fb, 0, &interface)
#   IOI2CInterfaceOpen(interface, 0, &connect)
#   IOI2CSendRequest(connect, 0, &request)   // request.sendAddress = 0x6E, etc.
# Rather than re-declaring the IOI2CRequest struct in ctypes, the pragmatic
# option is to shell out to ddcctl (https://github.com/kfix/ddcctl), or to just
# require an Apple Silicon Mac.