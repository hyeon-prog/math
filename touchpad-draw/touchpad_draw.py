"""터치패드 드로잉 오버레이 프로토타입.

Windows 정밀 터치패드(Precision Touchpad)의 HID 디지타이저 원시 입력을 읽어
화면 위 투명 오버레이 캔버스에 실시간으로 궤적을 그리고,
기호를 그린 뒤 잠시 멈추면 학습된 템플릿($P 인식기)과 비교해 텍스트로 변환한다.

사용법:
    python touchpad_draw.py                     # 실행 (F8로 드로잉 모드 토글)
    python touchpad_draw.py --train "0 1 + ="   # 나열한 기호들을 3번씩 그려 일괄 학습
    python touchpad_draw.py --probe             # 터치패드 감지 여부만 확인하고 종료
    python touchpad_draw.py --dump              # GUI 없이 터치 좌표를 콘솔에 출력

단축키 (드로잉 모드 중):
    F8·Esc      드로잉 모드 끄기 (인식 결과가 클립보드로 복사됨)
    Enter       화면의 기호들을 텍스트로 확정 (또는 1.2초 멈추면 자동,
                분수 작성 중으로 보이면 2.5초까지 기다림)
    T           마지막 기호를 학습 - 오인식된 기호 교정에도 사용
    Backspace   확정 전: 마지막 기호 취소 / 확정 후: 결과 글자 삭제
    Space       인식 결과에 공백 추가
    C           화면 전체 취소
    S           획 데이터 JSON 저장 (디버깅용)
    Ctrl+F8     프로그램 완전 종료

기호를 그리고 약 0.6초 멈추면 인식되어 회색 잉크와 라벨로 화면에 남는다.
옆으로 이어 쓴 글자는 멈추지 않아도 자동으로 분리 인식된다.
여러 기호를 이어 그린 뒤 Enter(또는 잠시 대기)로 텍스트 확정.
분수는 분자·가로 막대·분모를 위-가운데-아래로 그리면 (분자)/(분모)로 변환된다.
"""

import ctypes
import ctypes.wintypes as wt
import json
import os
import queue
import struct
import sys
import threading
import time

from recognizer import TemplateStore

# ---------------------------------------------------------------- 상수

USAGE_PAGE_DIGITIZER = 0x0D
USAGE_TOUCHPAD = 0x05
USAGE_PAGE_GENERIC = 0x01
USAGE_X = 0x30
USAGE_Y = 0x31
USAGE_TIP_SWITCH = 0x42

RIM_TYPEHID = 2
RIDEV_INPUTSINK = 0x00000100
RID_INPUT = 0x10000003
RIDI_PREPARSEDDATA = 0x20000005
RIDI_DEVICENAME = 0x20000007
RIDI_DEVICEINFO = 0x2000000B

HIDP_INPUT = 0
HIDP_STATUS_SUCCESS = 0x00110000

WM_INPUT = 0x00FF
WM_HOTKEY = 0x0312
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002

WH_MOUSE_LL = 14

VK_F8 = 0x77
VK_ESCAPE = 0x1B
VK_BACK = 0x08
VK_SPACE = 0x20
VK_RETURN = 0x0D
MOD_CONTROL = 0x0002

HOTKEY_TOGGLE = 1
HOTKEY_ESC = 2
HOTKEY_CLEAR = 3
HOTKEY_QUIT = 4
HOTKEY_SAVE = 5
HOTKEY_TRAIN = 6
HOTKEY_BACKSPACE = 7
HOTKEY_SPACE = 8
HOTKEY_COMMIT = 9

# 학습 라벨 입력창이 떠 있는 동안 마우스 잠금/단축키를 잠시 해제하기 위한 내부 메시지
WM_APP_SUSPEND = 0x8001
WM_APP_RESUME = 0x8002
# 마우스 차단 전용 스레드에 보내는 훅 설치/해제 메시지
WM_APP_BLOCK_ON = 0x8003
WM_APP_BLOCK_OFF = 0x8004

INK_COLOR = "#00E5FF"
INK_WIDTH = 6
TRANSPARENT_KEY = "#0f0e0d"  # 이 색으로 칠한 영역은 투명 처리됨
RECOG_PAUSE = 0.6            # 이 시간(초)만큼 획이 없으면 기호 하나로 확정
COMMIT_PAUSE_FAST = 1.2      # 이 시간 멈추면 화면의 기호들을 텍스트로 확정
COMMIT_PAUSE_SLOW = 2.5      # 분수 작성 중일 수 있으면(위쪽에 기호 존재) 더 기다림
TRAIN_SAMPLES = 3            # --train 모드에서 기호당 그릴 샘플 수
SPLIT_MARGIN = 0.03          # 옆으로 이만큼 이상 벗어난 새 획은 다른 기호로 분리

user32 = ctypes.windll.user32
hid = ctypes.windll.hid
kernel32 = ctypes.windll.kernel32

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wt.WPARAM, wt.LPARAM)

user32.CreateWindowExW.restype = wt.HWND
user32.SetWindowsHookExW.restype = wt.HANDLE
user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.CallNextHookEx.argtypes = [wt.HANDLE, ctypes.c_int, wt.WPARAM, wt.LPARAM]
user32.GetRawInputData.restype = wt.UINT
user32.GetRawInputData.argtypes = [
    wt.HANDLE, wt.UINT, ctypes.c_void_p, ctypes.POINTER(wt.UINT), wt.UINT]
user32.GetRawInputDeviceInfoW.restype = wt.UINT
user32.GetRawInputDeviceInfoW.argtypes = [
    wt.HANDLE, wt.UINT, ctypes.c_void_p, ctypes.POINTER(wt.UINT)]

kernel32.GlobalAlloc.restype = wt.HGLOBAL
kernel32.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [wt.HGLOBAL]
kernel32.GlobalUnlock.argtypes = [wt.HGLOBAL]
user32.SetClipboardData.argtypes = [wt.UINT, wt.HANDLE]

hid.HidP_GetCaps.restype = ctypes.c_long
hid.HidP_GetValueCaps.restype = ctypes.c_long
hid.HidP_GetUsageValue.restype = ctypes.c_long
hid.HidP_GetUsages.restype = ctypes.c_long
hid.HidP_MaxUsageListLength.restype = wt.ULONG

# ---------------------------------------------------------------- Win32 구조체


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wt.USHORT), ("usUsage", wt.USHORT),
                ("dwFlags", wt.DWORD), ("hwndTarget", wt.HWND)]


class RAWINPUTDEVICELIST(ctypes.Structure):
    _fields_ = [("hDevice", wt.HANDLE), ("dwType", wt.DWORD)]


class RID_DEVICE_INFO_HID(ctypes.Structure):
    _fields_ = [("dwVendorId", wt.DWORD), ("dwProductId", wt.DWORD),
                ("dwVersionNumber", wt.DWORD),
                ("usUsagePage", wt.USHORT), ("usUsage", wt.USHORT)]


class _RID_INFO_UNION(ctypes.Union):
    _fields_ = [("hid", RID_DEVICE_INFO_HID), ("_pad", ctypes.c_byte * 24)]


class RID_DEVICE_INFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("dwType", wt.DWORD), ("u", _RID_INFO_UNION)]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ("Usage", wt.USHORT), ("UsagePage", wt.USHORT),
        ("InputReportByteLength", wt.USHORT), ("OutputReportByteLength", wt.USHORT),
        ("FeatureReportByteLength", wt.USHORT), ("Reserved", wt.USHORT * 17),
        ("NumberLinkCollectionNodes", wt.USHORT),
        ("NumberInputButtonCaps", wt.USHORT), ("NumberInputValueCaps", wt.USHORT),
        ("NumberInputDataIndices", wt.USHORT),
        ("NumberOutputButtonCaps", wt.USHORT), ("NumberOutputValueCaps", wt.USHORT),
        ("NumberOutputDataIndices", wt.USHORT),
        ("NumberFeatureButtonCaps", wt.USHORT), ("NumberFeatureValueCaps", wt.USHORT),
        ("NumberFeatureDataIndices", wt.USHORT)]


class _VC_RANGE(ctypes.Structure):
    _fields_ = [("UsageMin", wt.USHORT), ("UsageMax", wt.USHORT),
                ("StringMin", wt.USHORT), ("StringMax", wt.USHORT),
                ("DesignatorMin", wt.USHORT), ("DesignatorMax", wt.USHORT),
                ("DataIndexMin", wt.USHORT), ("DataIndexMax", wt.USHORT)]


class _VC_NOTRANGE(ctypes.Structure):
    _fields_ = [("Usage", wt.USHORT), ("Reserved1", wt.USHORT),
                ("StringIndex", wt.USHORT), ("Reserved2", wt.USHORT),
                ("DesignatorIndex", wt.USHORT), ("Reserved3", wt.USHORT),
                ("DataIndex", wt.USHORT), ("Reserved4", wt.USHORT)]


class _VC_UNION(ctypes.Union):
    _fields_ = [("Range", _VC_RANGE), ("NotRange", _VC_NOTRANGE)]


class HIDP_VALUE_CAPS(ctypes.Structure):
    _fields_ = [
        ("UsagePage", wt.USHORT), ("ReportID", ctypes.c_ubyte),
        ("IsAlias", ctypes.c_ubyte), ("BitField", wt.USHORT),
        ("LinkCollection", wt.USHORT), ("LinkUsage", wt.USHORT),
        ("LinkUsagePage", wt.USHORT),
        ("IsRange", ctypes.c_ubyte), ("IsStringRange", ctypes.c_ubyte),
        ("IsDesignatorRange", ctypes.c_ubyte), ("IsAbsolute", ctypes.c_ubyte),
        ("HasNull", ctypes.c_ubyte), ("Reserved", ctypes.c_ubyte),
        ("BitSize", wt.USHORT), ("ReportCount", wt.USHORT),
        ("Reserved2", wt.USHORT * 5),
        ("UnitsExp", wt.ULONG), ("Units", wt.ULONG),
        ("LogicalMin", ctypes.c_long), ("LogicalMax", ctypes.c_long),
        ("PhysicalMin", ctypes.c_long), ("PhysicalMax", ctypes.c_long),
        ("u", _VC_UNION)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wt.HINSTANCE), ("hIcon", wt.HANDLE),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HANDLE),
                ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


_pin_rect = None


def pin_cursor(on):
    """커서를 현재 위치 1픽셀 영역에 고정/해제 (훅과 무관하게 커널이 강제)."""
    global _pin_rect
    if on:
        pt = wt.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        _pin_rect = RECT(pt.x, pt.y, pt.x + 1, pt.y + 1)
        user32.ClipCursor(ctypes.byref(_pin_rect))
    else:
        _pin_rect = None
        user32.ClipCursor(None)


def repin_cursor():
    """클립 다시 걸기. 포커스 전환(오버레이 표시, Alt+Tab 등)이 일어나면
    Windows가 ClipCursor를 자동 해제하므로 드로잉 중 주기적으로 재적용한다."""
    if _pin_rect is not None:
        user32.ClipCursor(ctypes.byref(_pin_rect))


class MouseBlocker(threading.Thread):
    """드로잉 중 마우스 이벤트(이동/클릭)를 삼키는 전용 스레드.

    HID 파싱 스레드와 분리해 훅 콜백이 지연되지 않게 한다. 콜백이 오래 밀리면
    Windows가 저수준 훅을 조용히 제거해 커서 차단이 풀리는 문제가 있었다.
    드로잉 모드마다 훅을 새로 설치해 제거된 상태가 누적되지 않게 한다.
    """

    def __init__(self):
        super().__init__(daemon=True)
        self.blocking = False
        self.tid = None
        self._hook = None
        self._hookproc = HOOKPROC(self._proc)
        self.ready = threading.Event()

    def run(self):
        self.tid = kernel32.GetCurrentThreadId()
        self.ready.set()
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_APP_BLOCK_ON and not self._hook:
                self._hook = user32.SetWindowsHookExW(
                    WH_MOUSE_LL, self._hookproc,
                    kernel32.GetModuleHandleW(None), 0)
                self.blocking = True
            elif msg.message == WM_APP_BLOCK_OFF and self._hook:
                self.blocking = False
                user32.UnhookWindowsHookEx(self._hook)
                self._hook = None

    def set_blocking(self, on):
        if self.tid is not None:
            user32.PostThreadMessageW(
                self.tid, WM_APP_BLOCK_ON if on else WM_APP_BLOCK_OFF, 0, 0)

    def _proc(self, ncode, wparam, lparam):
        if ncode >= 0 and self.blocking:
            return 1
        return user32.CallNextHookEx(None, ncode, wparam, lparam)


def copy_to_clipboard(text):
    """앱 종료 후에도 유지되도록 Win32 API로 직접 클립보드에 복사."""
    if not user32.OpenClipboard(None):
        return False
    try:
        user32.EmptyClipboard()
        data = text.encode("utf-16-le") + b"\x00\x00"
        handle = kernel32.GlobalAlloc(0x0002, len(data))  # GMEM_MOVEABLE
        if not handle:
            return False
        ptr = kernel32.GlobalLock(handle)
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(handle)
        return bool(user32.SetClipboardData(13, handle))  # CF_UNICODETEXT
    finally:
        user32.CloseClipboard()


# ---------------------------------------------------------------- HID 파싱


def _caps_matches_usage(vc, usage):
    if vc.IsRange:
        return vc.u.Range.UsageMin <= usage <= vc.u.Range.UsageMax
    return vc.u.NotRange.Usage == usage


class PadDevice:
    """터치패드 한 대의 preparsed data와 접점(finger) 컬렉션 정보."""

    def __init__(self, hdevice):
        size = wt.UINT(0)
        user32.GetRawInputDeviceInfoW(hdevice, RIDI_PREPARSEDDATA, None,
                                      ctypes.byref(size))
        if size.value == 0:
            raise OSError("preparsed data 크기를 얻지 못했습니다")
        self._pp_buf = ctypes.create_string_buffer(size.value)
        if user32.GetRawInputDeviceInfoW(hdevice, RIDI_PREPARSEDDATA,
                                         self._pp_buf,
                                         ctypes.byref(size)) == wt.UINT(-1).value:
            raise OSError("preparsed data를 읽지 못했습니다")
        self.pp = ctypes.cast(self._pp_buf, ctypes.c_void_p)

        caps = HIDP_CAPS()
        if hid.HidP_GetCaps(self.pp, ctypes.byref(caps)) != HIDP_STATUS_SUCCESS:
            raise OSError("HidP_GetCaps 실패")

        n = wt.USHORT(caps.NumberInputValueCaps)
        vcaps = (HIDP_VALUE_CAPS * max(n.value, 1))()
        hid.HidP_GetValueCaps(HIDP_INPUT, vcaps, ctypes.byref(n), self.pp)

        x_by_coll, y_by_coll = {}, {}
        for i in range(n.value):
            vc = vcaps[i]
            if vc.UsagePage != USAGE_PAGE_GENERIC or vc.LinkCollection == 0:
                continue
            rng = (vc.LogicalMin, vc.LogicalMax)
            if _caps_matches_usage(vc, USAGE_X):
                x_by_coll.setdefault(vc.LinkCollection, rng)
            if _caps_matches_usage(vc, USAGE_Y):
                y_by_coll.setdefault(vc.LinkCollection, rng)

        self.contacts = sorted(set(x_by_coll) & set(y_by_coll))
        if not self.contacts:
            raise OSError("X/Y 좌표를 보고하는 접점 컬렉션이 없습니다")
        self.x_range = {c: x_by_coll[c] for c in self.contacts}
        self.y_range = {c: y_by_coll[c] for c in self.contacts}

        c0 = self.contacts[0]
        xr = max(1, self.x_range[c0][1] - self.x_range[c0][0])
        yr = max(1, self.y_range[c0][1] - self.y_range[c0][0])
        self.aspect = xr / yr

        self._max_usages = min(
            64, max(1, hid.HidP_MaxUsageListLength(
                HIDP_INPUT, USAGE_PAGE_DIGITIZER, self.pp)))

    def _get_value(self, coll, usage, report, rlen):
        val = wt.ULONG(0)
        status = hid.HidP_GetUsageValue(
            HIDP_INPUT, USAGE_PAGE_GENERIC, coll, usage, ctypes.byref(val),
            self.pp, report, rlen)
        return val.value if status == HIDP_STATUS_SUCCESS else None

    def parse(self, report_bytes):
        """보고서 하나를 파싱해 (nx, ny, tip) 반환. 접촉 없으면 (None, None, False)."""
        report = ctypes.create_string_buffer(report_bytes, len(report_bytes))
        rlen = len(report_bytes)
        for coll in self.contacts:
            usages = (wt.USHORT * self._max_usages)()
            n = wt.ULONG(self._max_usages)
            status = hid.HidP_GetUsages(
                HIDP_INPUT, USAGE_PAGE_DIGITIZER, coll, usages,
                ctypes.byref(n), self.pp, report, rlen)
            if status != HIDP_STATUS_SUCCESS:
                continue
            if not any(usages[i] == USAGE_TIP_SWITCH for i in range(n.value)):
                continue
            x = self._get_value(coll, USAGE_X, report, rlen)
            y = self._get_value(coll, USAGE_Y, report, rlen)
            if x is None or y is None:
                continue
            xmin, xmax = self.x_range[coll]
            ymin, ymax = self.y_range[coll]
            nx = (x - xmin) / max(1, xmax - xmin)
            ny = (y - ymin) / max(1, ymax - ymin)
            return nx, ny, True
        return None, None, False


# ---------------------------------------------------------------- Raw Input 스레드


class TouchpadReader(threading.Thread):
    """숨김 윈도우로 WM_INPUT을 수신하고, 전역 단축키와 마우스 차단 훅을 관리한다."""

    def __init__(self, out_queue, blocker=None):
        super().__init__(daemon=True)
        self.q = out_queue
        self.blocker = blocker
        self.hwnd = None
        self.drawing = False
        self._locked = False
        self._devices = {}
        self._wndproc = WNDPROC(self._window_proc)
        self.ready = threading.Event()

    # ---- 스레드 본체

    def run(self):
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wndproc
        wc.hInstance = hinst
        wc.lpszClassName = "TouchpadDrawHiddenWnd"
        if not user32.RegisterClassW(ctypes.byref(wc)):
            self.q.put(("error", "윈도우 클래스 등록 실패"))
            return

        # 메시지 전용 윈도우는 Raw Input을 못 받으므로, 보이지 않는 일반 창을 만든다
        self.hwnd = user32.CreateWindowExW(
            0, wc.lpszClassName, "touchpad-draw", 0,
            0, 0, 0, 0, None, None, hinst, None)
        if not self.hwnd:
            self.q.put(("error", "숨김 윈도우 생성 실패"))
            return

        rid = RAWINPUTDEVICE(USAGE_PAGE_DIGITIZER, USAGE_TOUCHPAD,
                             RIDEV_INPUTSINK, self.hwnd)
        if not user32.RegisterRawInputDevices(ctypes.byref(rid), 1,
                                              ctypes.sizeof(RAWINPUTDEVICE)):
            self.q.put(("error", "Raw Input 등록 실패 - 정밀 터치패드가 없을 수 있습니다"))
            return

        if not user32.RegisterHotKey(self.hwnd, HOTKEY_TOGGLE, 0, VK_F8):
            self.q.put(("warn", "F8 전역 단축키 등록 실패 (다른 프로그램이 사용 중)"))
        user32.RegisterHotKey(self.hwnd, HOTKEY_QUIT, MOD_CONTROL, VK_F8)

        self.ready.set()
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        self._set_drawing(False)

    def stop(self):
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)

    # ---- 드로잉 모드 전환

    def _set_drawing(self, on):
        if on == self.drawing:
            return
        self.drawing = on
        self._apply_lock(on)
        self.q.put(("mode", on))

    def _apply_lock(self, on):
        """커서 고정, 마우스 차단, 드로잉 모드 단축키를 설치/해제한다."""
        if on == self._locked:
            return
        self._locked = on
        if on:
            if self.blocker:
                self.blocker.set_blocking(True)
            pin_cursor(True)
            user32.RegisterHotKey(self.hwnd, HOTKEY_ESC, 0, VK_ESCAPE)
            user32.RegisterHotKey(self.hwnd, HOTKEY_CLEAR, 0, ord('C'))
            user32.RegisterHotKey(self.hwnd, HOTKEY_SAVE, 0, ord('S'))
            user32.RegisterHotKey(self.hwnd, HOTKEY_TRAIN, 0, ord('T'))
            user32.RegisterHotKey(self.hwnd, HOTKEY_BACKSPACE, 0, VK_BACK)
            user32.RegisterHotKey(self.hwnd, HOTKEY_SPACE, 0, VK_SPACE)
            user32.RegisterHotKey(self.hwnd, HOTKEY_COMMIT, 0, VK_RETURN)
        else:
            pin_cursor(False)
            if self.blocker:
                self.blocker.set_blocking(False)
            for hk in (HOTKEY_ESC, HOTKEY_CLEAR, HOTKEY_SAVE, HOTKEY_TRAIN,
                       HOTKEY_BACKSPACE, HOTKEY_SPACE, HOTKEY_COMMIT):
                user32.UnregisterHotKey(self.hwnd, hk)

    # ---- 윈도우 프로시저

    def _window_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_INPUT:
            self._on_raw_input(lparam)
        elif msg == WM_HOTKEY:
            if wparam == HOTKEY_TOGGLE:
                self._set_drawing(not self.drawing)
            elif wparam == HOTKEY_ESC:
                self._set_drawing(False)
            elif wparam == HOTKEY_CLEAR:
                self.q.put(("clear",))
            elif wparam == HOTKEY_SAVE:
                self.q.put(("save",))
            elif wparam == HOTKEY_TRAIN:
                self.q.put(("train",))
            elif wparam == HOTKEY_BACKSPACE:
                self.q.put(("backspace",))
            elif wparam == HOTKEY_SPACE:
                self.q.put(("space",))
            elif wparam == HOTKEY_COMMIT:
                self.q.put(("commit",))
            elif wparam == HOTKEY_QUIT:
                self._set_drawing(False)
                self.q.put(("quit",))
                user32.PostQuitMessage(0)
            return 0
        elif msg == WM_APP_SUSPEND:
            self._apply_lock(False)
            return 0
        elif msg == WM_APP_RESUME:
            if self.drawing:
                self._apply_lock(True)
            return 0
        elif msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _on_raw_input(self, lparam):
        hraw = ctypes.c_void_p(lparam & 0xFFFFFFFFFFFFFFFF)
        size = wt.UINT(0)
        header_size = 24 if ctypes.sizeof(ctypes.c_void_p) == 8 else 16
        user32.GetRawInputData(hraw, RID_INPUT, None, ctypes.byref(size),
                               header_size)
        if size.value == 0:
            return
        buf = ctypes.create_string_buffer(size.value)
        if user32.GetRawInputData(hraw, RID_INPUT, buf, ctypes.byref(size),
                                  header_size) == wt.UINT(-1).value:
            return

        dw_type, = struct.unpack_from("<I", buf, 0)
        if dw_type != RIM_TYPEHID:
            return
        hdevice = struct.unpack_from("<Q" if header_size == 24 else "<I",
                                     buf, 8)[0]
        size_hid, count = struct.unpack_from("<II", buf, header_size)

        dev = self._devices.get(hdevice)
        if dev is None:
            try:
                dev = PadDevice(ctypes.c_void_p(hdevice))
            except OSError:
                dev = False  # 파싱 불가 장치는 다시 시도하지 않음
            self._devices[hdevice] = dev
        if not dev:
            return

        data_off = header_size + 8
        for i in range(count):
            report = buf.raw[data_off + i * size_hid:
                             data_off + (i + 1) * size_hid]
            nx, ny, tip = dev.parse(report)
            if self.drawing:
                self.q.put(("contact", nx, ny, tip, dev.aspect))


# ------------------------------------------------- 공간 배치 해석 (분수)


def _cx(it):
    b = it["bbox"]
    return (b[0] + b[2]) / 2


def _cy(it):
    b = it["bbox"]
    return (b[1] + b[3]) / 2


def _wrap(s):
    return s if len(s) <= 1 else f"({s})"


def layout_to_text(entries):
    """기호들의 위치 관계를 해석해 텍스트로 변환. 분수(위-막대-아래)를 지원."""
    items = [{"label": e["label"], "bbox": e["bbox"]} for e in entries]
    return _parse_layout(items)


def _parse_layout(items):
    if not items:
        return ""
    # 분수 막대 후보: '-'로 인식된 기호 중, 가로 범위 안에 위/아래 기호가 모두 있는 것.
    # 여러 개면 가장 넓은 것부터 (바깥 분수가 안쪽 분수보다 넓다고 가정)
    best = None
    for bar in items:
        if bar["label"] != "-":
            continue
        x0, _, x1, _ = bar["bbox"]
        cy_bar = _cy(bar)
        above = [t for t in items if t is not bar
                 and x0 <= _cx(t) <= x1 and _cy(t) < cy_bar]
        below = [t for t in items if t is not bar
                 and x0 <= _cx(t) <= x1 and _cy(t) > cy_bar]
        if above and below:
            width = x1 - x0
            if best is None or width > best[0]:
                best = (width, bar, above, below)
    if best is None:
        return "".join(t["label"] for t in sorted(items, key=_cx))
    _, bar, above, below = best
    frac = f"{_wrap(_parse_layout(above))}/{_wrap(_parse_layout(below))}"
    used = {id(bar)} | {id(t) for t in above} | {id(t) for t in below}
    rest = [t for t in items if id(t) not in used]
    rest.append({"label": frac, "bbox": bar["bbox"]})
    return _parse_layout(rest)


# ---------------------------------------------------------------- 오버레이 GUI


class OverlayApp:
    def __init__(self, q, reader, train_labels=None):
        import tkinter as tk
        self.tk = tk
        self.q = q
        self.reader = reader
        self.store = TemplateStore(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "templates.json"))
        self.result = ""           # 지금까지 확정된 텍스트
        self.expr = []             # 인식됐지만 아직 텍스트로 확정 전인 기호들
        self._sym_seq = 0          # 기호별 캔버스 태그 일련번호
        self.last_symbol = None    # 마지막으로 인식된 기호의 획들 (T키 학습용)
        self.dialog_open = False
        self.mode_on = False       # 드로잉 모드 여부 (커서 고정 재적용에 사용)
        self.train_queue = []      # [(라벨, 몇 번째 샘플, 전체 수), ...]
        if train_labels:
            for label in train_labels:
                for i in range(1, TRAIN_SAMPLES + 1):
                    self.train_queue.append((label, i, TRAIN_SAMPLES))

        self.root = tk.Tk()
        self.root.title("touchpad-draw")
        self.root.configure(bg=TRANSPARENT_KEY)
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", TRANSPARENT_KEY)
        self.root.withdraw()

        self.sw = self.root.winfo_screenwidth()
        self.sh = self.root.winfo_screenheight()
        self.canvas = tk.Canvas(self.root, bg=TRANSPARENT_KEY,
                                highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.aspect = 1.5          # 터치패드 가로/세로 비율 (첫 접촉 시 갱신)
        self.region = None         # 터치패드가 매핑되는 화면 영역 (x, y, w, h)
        self.strokes = []          # 인식 대기 중인 획들 [[(x, y), ...], ...]
        self.stroke_tags = []      # strokes와 1:1 대응하는 캔버스 태그
        self._stroke_seq = 0
        self.cur = None            # 진행 중인 획
        self.cur_tag = None
        self.prev_px = None        # 직전 화면 좌표
        self.prev_tip = False
        self.last_contact = 0.0
        self._hint_id = None
        self._result_id = None
        self._flash_id = None

    # ---- 좌표 매핑

    def _compute_region(self):
        margin = 60
        avail_w, avail_h = self.sw - 2 * margin, self.sh - 2 * margin
        if avail_w / avail_h > self.aspect:
            h = avail_h
            w = h * self.aspect
        else:
            w = avail_w
            h = w / self.aspect
        self.region = ((self.sw - w) / 2, (self.sh - h) / 2, w, h)

    def _to_screen(self, nx, ny):
        rx, ry, rw, rh = self.region
        return rx + nx * rw, ry + ny * rh

    def _true_to_screen(self, x, y):
        """실제 종횡비 좌표(획 저장 좌표)를 화면 좌표로."""
        return self._to_screen(x / self.aspect, y)

    # ---- 화면 요소

    def _draw_chrome(self):
        self.canvas.delete("chrome")
        rx, ry, rw, rh = self.region
        self.canvas.create_rectangle(rx, ry, rx + rw, ry + rh,
                                     outline="#666666", dash=(6, 4),
                                     width=2, tags="chrome")
        bar_w = 980
        self.canvas.create_rectangle(
            (self.sw - bar_w) / 2, 8, (self.sw + bar_w) / 2, 100,
            fill="#1c1c1c", outline="#444444", tags="chrome")
        self._result_id = self.canvas.create_text(
            self.sw / 2, 44, fill="#ffffff",
            font=("Malgun Gothic", 22, "bold"), text="", tags="chrome")
        self._hint_id = self.canvas.create_text(
            self.sw / 2, 82, fill="#bbbbbb",
            font=("Malgun Gothic", 10),
            text=self._default_status(), tags="chrome")
        self._update_result()

    def _default_status(self):
        if self.train_queue:
            label, idx, total = self.train_queue[0]
            return (f"학습 모드 — '{label}' 그리기 ({idx}/{total})   "
                    "그린 뒤 잠시 멈추면 자동 저장   |   Esc·F8: 종료")
        return ("기호 그리고 멈추면 인식 · Enter 또는 잠시 멈추면 텍스트 확정   |   "
                "분수: 분자·막대·분모를 위-가운데-아래로   |   T: 교정   "
                "Backspace: 취소/삭제   C: 전체 취소   Esc: 종료(클립보드 복사)")

    def _update_result(self):
        if self._result_id:
            self.canvas.itemconfigure(self._result_id, text=self.result[-48:])

    def _flash(self, text, ms=2200):
        self.canvas.itemconfigure(self._hint_id, text=text)
        if self._flash_id:
            self.root.after_cancel(self._flash_id)
        self._flash_id = self.root.after(
            ms, lambda: self.canvas.itemconfigure(
                self._hint_id, text=self._default_status()))

    # ---- 획 처리

    def _start_stroke(self, pt):
        self.cur = [pt]
        self.cur_tag = f"st{self._stroke_seq}"
        self._stroke_seq += 1

    def _is_new_symbol(self, stroke):
        """새 획이 다른 기호의 시작이면 True (대기 획들을 즉시 확정시킴).

        1) 가로 분리: 새 획이 옆으로 떨어져 있으면 다른 글자.
           중심점 포함 검사라 +, =, t처럼 획이 겹치는 다획 기호는 안 분리됨.
        2) 분수 세로 분리: 시간 대기 없이 분자-막대-분모를 나누기 위한 규칙.
        """
        ax0 = min(p[0] for s in self.strokes for p in s)
        ax1 = max(p[0] for s in self.strokes for p in s)
        ay0 = min(p[1] for s in self.strokes for p in s)
        ay1 = max(p[1] for s in self.strokes for p in s)
        bx0 = min(p[0] for p in stroke)
        bx1 = max(p[0] for p in stroke)
        by0 = min(p[1] for p in stroke)
        by1 = max(p[1] for p in stroke)
        m = SPLIT_MARGIN
        acx, bcx = (ax0 + ax1) / 2, (bx0 + bx1) / 2
        # 가로로 떨어져 있으면 무조건 다른 글자
        if not (ax0 - m <= bcx <= ax1 + m or bx0 - m <= acx <= bx1 + m):
            return True
        aw, bw, bh = ax1 - ax0, bx1 - bx0, by1 - by0
        bcy = (by0 + by1) / 2
        # 분자 -> 막대: 새 획이 납작하고(가로선) 기존보다 확실히 넓으며 아래에 있음.
        # '='는 두 획의 너비가 비슷해 1.3배 조건에 걸리지 않는다.
        if (bw >= 4 * bh and bw >= 1.3 * aw and bw >= 0.12
                and bcy > ay1 - 0.02 and bx0 - m <= acx <= bx1 + m):
            return True
        # 막대 -> 분모: 대기 중인 게 납작한 가로선 하나이고 그 위에 이미 확정된
        # 기호(분자)가 있으면 분수 막대가 확실하므로, 아래의 새 획은 분모.
        if (len(self.strokes) == 1 and aw >= 4 * (ay1 - ay0) and aw >= 0.12
                and bcy > ay1 - 0.02):
            for e in self.expr:
                ex0, ey0, ex1, ey1 = e["bbox"]
                if ey1 < ay0 + 0.03 and ax0 - m <= (ex0 + ex1) / 2 <= ax1 + m:
                    return True
        return False

    def _end_stroke(self):
        if self.cur and len(self.cur) > 1:
            stroke, tag = self.cur, self.cur_tag
            # 옆에 쓴 새 글자면 이전 기호를 먼저 확정 (빠르게 이어 써도 분리됨)
            if (self.strokes and not self.train_queue
                    and self._is_new_symbol(stroke)):
                self._finish_symbol()
            self.strokes.append(stroke)
            self.stroke_tags.append(tag)
        elif self.cur and self.cur_tag:
            self.canvas.delete(self.cur_tag)  # 점 하나짜리 획은 무시
        self.cur = None
        self.cur_tag = None
        self.prev_px = None

    def _on_contact(self, nx, ny, tip, aspect):
        self.last_contact = time.time()
        if abs(aspect - self.aspect) > 0.01:
            self.aspect = aspect
            self._compute_region()
            self._draw_chrome()
        if not tip:
            self._end_stroke()
            self.prev_tip = False
            return

        px, py = self._to_screen(nx, ny)
        # 저장 좌표는 실제 종횡비 기준 (외부 데이터셋 템플릿과 모양 비교를 위해)
        pt = (nx * self.aspect, ny)
        if self.prev_tip and self.cur:
            lx, ly = self.prev_px
            # 손가락이 순간이동한 경우(다른 손가락으로 교체 등)는 새 획으로
            if ((px - lx) ** 2 + (py - ly) ** 2) ** 0.5 > 0.35 * self.sw:
                self._end_stroke()
                self._start_stroke(pt)
            else:
                if ((px - lx) ** 2 + (py - ly) ** 2) ** 0.5 >= 1.5:
                    self.canvas.create_line(lx, ly, px, py,
                                            fill=INK_COLOR, width=INK_WIDTH,
                                            capstyle="round", smooth=True,
                                            tags=("ink", self.cur_tag))
                    self.cur.append(pt)
                else:
                    self.prev_tip = True
                    return
        else:
            self._start_stroke(pt)
        self.prev_px = (px, py)
        self.prev_tip = True

    def _clear(self):
        self.canvas.delete("ink")
        for e in self.expr:
            self.canvas.delete(e["tag"])
        self.expr = []
        self.strokes = []
        self.stroke_tags = []
        self.cur = None
        self.cur_tag = None
        self.prev_px = None

    def _finish_symbol(self):
        """대기 중인 획 묶음을 기호 하나로 인식한다."""
        strokes, tags = self.strokes, self.stroke_tags
        self.strokes, self.stroke_tags = [], []
        self.last_symbol = strokes
        if self.train_queue:
            for t in tags:
                self.canvas.delete(t)
            label, idx, total = self.train_queue.pop(0)
            self.store.add(label, strokes)
            if self.train_queue:
                self._flash(f"'{label}' 저장됨 ({idx}/{total})", 900)
            else:
                self._flash("학습 완료! 이제 기호를 그리면 인식됩니다")
            return
        xs = [p[0] for s in strokes for p in s]
        ys = [p[1] for s in strokes for p in s]
        bbox = (min(xs), min(ys), max(xs), max(ys))
        diag = ((bbox[2] - bbox[0]) ** 2 + (bbox[3] - bbox[1]) ** 2) ** 0.5
        if diag < 0.06:  # 아주 작은 입력은 점(.) - 크기가 정규화되면 구분 불가
            label, note = ".", "작은 입력은 점으로 처리"
        else:
            cands = self.store.recognize(strokes)
            if not cands:
                for t in tags:
                    self.canvas.delete(t)
                self._flash("학습된 기호가 없습니다 — 방금 그린 기호를 T키로 학습하세요")
                return
            label = cands[0][0]
            note = "후보: " + "   ".join(f"{l} ({d:.2f})" for l, d in cands)
        # 인식된 기호의 잉크는 회색으로 화면에 남기고 위에 라벨을 표시
        tag = f"sym{self._sym_seq}"
        self._sym_seq += 1
        for t in tags:
            self.canvas.addtag_withtag(tag, t)
        self.canvas.dtag(tag, "ink")
        self.canvas.itemconfigure(tag, fill="#8a8a8a")
        sx, sy = self._true_to_screen((bbox[0] + bbox[2]) / 2, bbox[1])
        text_id = self.canvas.create_text(
            sx, max(sy - 16, 12), fill="#9adfff",
            font=("Malgun Gothic", 11, "bold"), text=label, tags=tag)
        self.expr.append({"label": label, "bbox": bbox, "tag": tag,
                          "text_id": text_id, "strokes": strokes})
        self._flash(f"인식: {label}   ({note})   |   Enter 또는 잠시 멈추면 텍스트 확정")

    def _commit_expr(self):
        """화면에 쌓인 기호들을 위치 관계(분수 등)로 해석해 결과 텍스트에 붙인다."""
        if not self.expr:
            return
        text = layout_to_text(self.expr)
        for e in self.expr:
            self.canvas.delete(e["tag"])
        self.expr = []
        self.result += text
        self._update_result()
        self._flash(f"입력됨: {text}")

    def _train_dialog(self):
        """T키: 방금 그린 기호에 라벨을 붙여 학습. 오인식 교정을 겸한다."""
        from tkinter import simpledialog
        if self.train_queue:
            self._flash("일괄 학습 중에는 T키를 사용할 수 없습니다")
            return
        if self.strokes or self.cur:
            # 아직 인식 전인 획이 있으면 먼저 기호로 인식시킨 뒤 교정 대상으로
            self._end_stroke()
            if self.strokes:
                self._finish_symbol()
        if not self.last_symbol:
            self._flash("학습할 기호가 없습니다 — 먼저 기호를 그리세요")
            return
        self.dialog_open = True
        user32.PostMessageW(self.reader.hwnd, WM_APP_SUSPEND, 0, 0)
        try:
            label = simpledialog.askstring(
                "기호 학습", "방금 그린 기호로 출력할 문자를 입력하세요:",
                parent=self.root)
        finally:
            user32.PostMessageW(self.reader.hwnd, WM_APP_RESUME, 0, 0)
            self.dialog_open = False
        label = (label or "").strip()
        if not label:
            return
        self.store.add(label, self.last_symbol)
        # 확정 전인 마지막 기호였다면 라벨을 올바르게 교체
        if self.expr and self.expr[-1]["strokes"] is self.last_symbol:
            self.expr[-1]["label"] = label
            self.canvas.itemconfigure(self.expr[-1]["text_id"], text=label)
        self._flash(f"'{label}' 학습 완료 (샘플 {self.store.count(label)}개)")

    def _save(self):
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "captures")
        os.makedirs(out_dir, exist_ok=True)
        self._end_stroke()
        path = os.path.join(out_dir,
                            time.strftime("strokes_%Y%m%d_%H%M%S.json"))
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"aspect": self.aspect, "strokes": self.strokes}, f)
        self._flash(f"저장됨: {os.path.basename(path)} ({len(self.strokes)}획)")

    # ---- 이벤트 루프

    def _poll(self):
        try:
            while True:
                ev = self.q.get_nowait()
                kind = ev[0]
                if kind == "contact":
                    if not self.dialog_open:
                        self._on_contact(*ev[1:])
                elif kind == "mode":
                    self.mode_on = ev[1]
                    if ev[1]:
                        self._compute_region()
                        self.root.deiconify()
                        self.root.lift()
                        self._draw_chrome()
                    else:
                        self._end_stroke()
                        self._commit_expr()
                        self._clear()
                        self.root.withdraw()
                        if self.result and copy_to_clipboard(self.result):
                            print(f"인식 결과(클립보드에 복사됨): {self.result}")
                elif kind == "clear":
                    self._clear()
                elif kind == "save":
                    self._save()
                elif kind == "train":
                    if not self.dialog_open:
                        self.root.after(10, self._train_dialog)
                elif kind == "commit":
                    if not self.dialog_open:
                        self._end_stroke()
                        if self.strokes:
                            self._finish_symbol()
                        self._commit_expr()
                elif kind == "backspace":
                    if self.strokes or self.cur:
                        self._end_stroke()
                        self.strokes = []
                        self.stroke_tags = []
                        self.canvas.delete("ink")
                    elif self.expr:
                        e = self.expr.pop()
                        self.canvas.delete(e["tag"])
                    elif self.result:
                        self.result = self.result[:-1]
                        self._update_result()
                elif kind == "space":
                    self.result += " "
                    self._update_result()
                elif kind == "quit":
                    if self.result:
                        copy_to_clipboard(self.result)
                        print(f"인식 결과: {self.result}")
                    self.root.destroy()
                    return
                elif kind in ("error", "warn"):
                    print(f"[{kind}] {ev[1]}", file=sys.stderr)
                    if kind == "error":
                        self.root.destroy()
                        return
        except queue.Empty:
            pass
        # 접촉 신호가 끊긴 채 남아있는 획은 자동으로 마감
        now = time.time()
        if self.cur and now - self.last_contact > 0.3:
            self._end_stroke()
        # 획이 있고 일정 시간 새 입력이 없으면 기호 하나로 확정 -> 인식/학습
        if (not self.dialog_open and self.strokes and self.cur is None
                and now - self.last_contact > RECOG_PAUSE):
            self._finish_symbol()
        # 인식된 기호들이 있고 더 긴 멈춤이면 위치 해석 후 텍스트로 확정
        if (not self.dialog_open and self.expr and not self.strokes
                and self.cur is None
                and now - self.last_contact > self._commit_delay()):
            self._commit_expr()
        # 포커스 전환으로 Windows가 커서 클립을 풀어도 다시 고정
        if self.mode_on and not self.dialog_open:
            repin_cursor()
        self.root.after(8, self._poll)

    def _commit_delay(self):
        """패드 위쪽에 그린 기호(분자일 가능성)가 있으면 분수 완성을 기다린다."""
        for e in self.expr:
            if (e["bbox"][1] + e["bbox"][3]) / 2 < 0.45:
                return COMMIT_PAUSE_SLOW
        return COMMIT_PAUSE_FAST

    def _splash(self):
        """바로가기(콘솔 없음)로 실행해도 시작을 알 수 있게 잠깐 배너 표시."""
        tk = self.tk
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        tk.Label(win,
                 text="터치패드 수학입력 실행 중 — F8: 드로잉 시작  ·  Ctrl+F8: 종료",
                 bg="#1c1c1c", fg="#ffffff", font=("Malgun Gothic", 11),
                 padx=18, pady=10).pack()
        win.update_idletasks()
        win.geometry(f"+{(self.sw - win.winfo_width()) // 2}+40")
        win.after(3000, win.destroy)

    def run(self):
        self.root.after(8, self._poll)
        self._splash()
        if self.train_queue:
            labels = " ".join(dict.fromkeys(l for l, _, _ in self.train_queue))
            print(f"학습 모드 [{labels}] — F8을 눌러 시작하세요. (Ctrl+F8: 종료)")
        else:
            print(f"학습된 기호 {self.store.count()}종 로드됨. "
                  "F8을 눌러 드로잉 모드를 켜세요. (Ctrl+F8: 종료)")
        self.root.mainloop()
        self.reader.stop()


# ---------------------------------------------------------------- 진단 모드


def probe():
    n = wt.UINT(0)
    user32.GetRawInputDeviceList(None, ctypes.byref(n),
                                 ctypes.sizeof(RAWINPUTDEVICELIST))
    devices = (RAWINPUTDEVICELIST * max(n.value, 1))()
    user32.GetRawInputDeviceList(devices, ctypes.byref(n),
                                 ctypes.sizeof(RAWINPUTDEVICELIST))

    found = 0
    for i in range(n.value):
        if devices[i].dwType != RIM_TYPEHID:
            continue
        info = RID_DEVICE_INFO()
        info.cbSize = ctypes.sizeof(RID_DEVICE_INFO)
        size = wt.UINT(info.cbSize)
        user32.GetRawInputDeviceInfoW(devices[i].hDevice, RIDI_DEVICEINFO,
                                      ctypes.byref(info), ctypes.byref(size))
        if (info.u.hid.usUsagePage != USAGE_PAGE_DIGITIZER
                or info.u.hid.usUsage != USAGE_TOUCHPAD):
            continue
        found += 1
        print(f"정밀 터치패드 발견 (VID={info.u.hid.dwVendorId:04X} "
              f"PID={info.u.hid.dwProductId:04X})")
        try:
            dev = PadDevice(devices[i].hDevice)
            c0 = dev.contacts[0]
            print(f"  접점 컬렉션: {len(dev.contacts)}개 (최대 동시 터치 수)")
            print(f"  X 범위: {dev.x_range[c0]}, Y 범위: {dev.y_range[c0]}")
            print(f"  가로/세로 비율: {dev.aspect:.2f}")
        except OSError as e:
            print(f"  [경고] HID 파싱 실패: {e}")
    if found == 0:
        print("정밀 터치패드를 찾지 못했습니다.")
        print("설정 > Bluetooth 및 장치 > 터치패드에서 '정밀 터치패드' 여부를 확인하세요.")
    return found


def dump():
    q = queue.Queue()
    reader = TouchpadReader(q)
    reader.start()
    reader.ready.wait(3)
    print("F8을 눌러 드로잉 모드를 켠 뒤 터치패드를 만져보세요. Ctrl+C로 종료.")
    try:
        while True:
            try:
                ev = q.get(timeout=0.5)
            except queue.Empty:
                continue
            print(ev)
            if ev[0] == "quit":
                break
    except KeyboardInterrupt:
        pass
    reader.stop()


def main():
    if sys.platform != "win32":
        sys.exit("이 프로그램은 Windows 전용입니다.")
    # pythonw(콘솔 없는 실행)에서는 stdout/stderr가 None이라 print가 죽는 것 방지
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    # 콘솔 코드페이지(cp949)에서 특수문자 출력이 죽지 않도록
    for stream in (sys.stdout, sys.stderr):
        if stream:
            stream.reconfigure(encoding="utf-8", errors="replace")
    # 고해상도(DPI 스케일링) 화면에서 좌표가 어긋나지 않도록
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        ctypes.windll.shcore.SetProcessDpiAwareness(2)

    # 중복 실행 방지 (바로가기 두 번 클릭 등)
    kernel32.CreateMutexW(None, False, "touchpad_draw_single_instance")
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        user32.MessageBoxW(None, "이미 실행 중입니다.\nF8을 눌러 드로잉을 시작하세요.",
                           "터치패드 수학입력", 0x40)
        sys.exit(0)

    if "--probe" in sys.argv:
        sys.exit(0 if probe() else 1)
    if "--dump" in sys.argv:
        dump()
        return
    train_labels = None
    if "--train" in sys.argv:
        i = sys.argv.index("--train")
        if i + 1 >= len(sys.argv) or not sys.argv[i + 1].split():
            sys.exit('사용법: python touchpad_draw.py --train "0 1 2 + ="')
        train_labels = sys.argv[i + 1].split()

    if not probe():
        sys.exit(1)
    q = queue.Queue()
    blocker = MouseBlocker()
    blocker.start()
    blocker.ready.wait(3)
    reader = TouchpadReader(q, blocker)
    reader.start()
    if not reader.ready.wait(3):
        sys.exit("터치패드 리더 초기화 실패")
    OverlayApp(q, reader, train_labels).run()


if __name__ == "__main__":
    main()
