"""
mouse_tuner.py  ─  マウス感度・加速・スムーズカーブ リアルタイム調整
Windows SystemParametersInfo + Registry  /  再起動不要

タブ1: 基本設定
  - ポインタ速度 (SPI_SETMOUSESPEED)
  - 加速レベル 0/1/2 (SPI_SETMOUSE [2])
  - 閾値 T1/T2     (SPI_SETMOUSE [0][1])

タブ2: スムーズカーブ
  - SmoothMouseXCurve / SmoothMouseYCurve (HKCU\\Control Panel\\Mouse)
  - 5制御点の Y値 (倍率) をスライダー + Spinbox で編集
  - プリセット付き / キャンバスでリアルタイムプレビュー
"""

import ctypes, sys, platform
import tkinter as tk
from tkinter import ttk

if platform.system() != "Windows":
    sys.exit("このツールは Windows 専用です。")

import winreg  # noqa: E402  Windows のみ

# ═══════════════════════════════════════════════════════════════════
#  Win32 / Registry 定数
# ═══════════════════════════════════════════════════════════════════

SPI_GETMOUSE       = 0x0003
SPI_SETMOUSE       = 0x0004
SPI_GETMOUSESPEED  = 0x0070
SPI_SETMOUSESPEED  = 0x0071
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDCHANGE    = 0x02

MOUSE_REG_KEY = r"Control Panel\Mouse"

user32 = ctypes.windll.user32

# ═══════════════════════════════════════════════════════════════════
#  API ラッパー
# ═══════════════════════════════════════════════════════════════════

def get_mouse_speed() -> int:
    s = ctypes.c_int(0)
    user32.SystemParametersInfoW(SPI_GETMOUSESPEED, 0, ctypes.byref(s), 0)
    return s.value

def set_mouse_speed(v: int, persist: bool = False) -> None:
    f = (SPIF_UPDATEINIFILE | SPIF_SENDCHANGE) if persist else SPIF_SENDCHANGE
    user32.SystemParametersInfoW(SPI_SETMOUSESPEED, 0, v, f)

def get_mouse_params() -> tuple[int, int, int]:
    """(threshold1, threshold2, accel_level 0/1/2)"""
    p = (ctypes.c_int * 3)()
    user32.SystemParametersInfoW(SPI_GETMOUSE, 0, p, 0)
    return p[0], p[1], p[2]

def set_mouse_params(t1: int, t2: int, accel: int, persist: bool = False) -> None:
    f = (SPIF_UPDATEINIFILE | SPIF_SENDCHANGE) if persist else SPIF_SENDCHANGE
    p = (ctypes.c_int * 3)(t1, t2, accel)
    user32.SystemParametersInfoW(SPI_SETMOUSE, 0, p, f)

# ───────────────────────────────────────────────────────────────────
#  64bit 固定小数点 (SmoothMouseCurve の内部フォーマット)
#    格納レイアウト: [fractional 4B LE][integer 4B LE]
# ───────────────────────────────────────────────────────────────────

def _fixed64_decode(data: bytes, offset: int) -> float:
    lo = int.from_bytes(data[offset:offset + 4], "little")      # 小数部
    hi = int.from_bytes(data[offset + 4:offset + 8], "little")  # 整数部
    return hi + lo / 2**32

def _fixed64_encode(v: float) -> bytes:
    v = max(0.0, v)
    hi = int(v)
    lo = round((v - hi) * 2**32)
    if lo >= 2**32:
        lo = 0; hi += 1
    return lo.to_bytes(4, "little") + hi.to_bytes(4, "little")

# ───────────────────────────────────────────────────────────────────
#  スムーズカーブ
# ───────────────────────────────────────────────────────────────────

SMOOTH_X_DEFAULT = [0.0, 15.0, 31.0, 46.0, 61.0]   # 入力速度 (mickey/tick)
SMOOTH_Y_DEFAULT = [0.0, 0.75, 1.5,  2.25, 3.0  ]   # 出力倍率

def get_smooth_curve() -> tuple[list[float], list[float]]:
    """Registry から (x_points[5], y_points[5]) を返す。キーがなければデフォルト。"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, MOUSE_REG_KEY) as k:
            xd, _ = winreg.QueryValueEx(k, "SmoothMouseXCurve")
            yd, _ = winreg.QueryValueEx(k, "SmoothMouseYCurve")
        xs = [_fixed64_decode(xd, i * 8) for i in range(5)]
        ys = [_fixed64_decode(yd, i * 8) for i in range(5)]
        return xs, ys
    except Exception:
        return list(SMOOTH_X_DEFAULT), list(SMOOTH_Y_DEFAULT)

def set_smooth_curve(xs: list[float], ys: list[float], persist: bool = True) -> None:
    """Registry に書き込み、WM_SETTINGCHANGE をブロードキャストして即時反映。"""
    xb = b"".join(_fixed64_encode(v) for v in xs)
    yb = b"".join(_fixed64_encode(v) for v in ys)
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, MOUSE_REG_KEY,
        access=winreg.KEY_SET_VALUE,
    ) as k:
        winreg.SetValueEx(k, "SmoothMouseXCurve", 0, winreg.REG_BINARY, xb)
        winreg.SetValueEx(k, "SmoothMouseYCurve", 0, winreg.REG_BINARY, yb)
    # 即時反映: 現在の SPI_SETMOUSE 値を SPIF_SENDCHANGE 付きで再送
    p = (ctypes.c_int * 3)()
    user32.SystemParametersInfoW(SPI_GETMOUSE, 0, p, 0)
    user32.SystemParametersInfoW(
        SPI_SETMOUSE, 0, p, SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
    )

# ═══════════════════════════════════════════════════════════════════
#  テーマ定数
# ═══════════════════════════════════════════════════════════════════

BG      = "#0f0f12"
SURFACE = "#1a1a20"
ACCENT  = "#00e5a0"
TEXT    = "#e8e8f0"
MUTED   = "#6b6b80"
DIM     = "#2a2a35"

# ═══════════════════════════════════════════════════════════════════
#  ウィジェット
# ═══════════════════════════════════════════════════════════════════

class LinkedSliderSpin(tk.Frame):
    """整数値: Scale と Spinbox を連動させるウィジェット"""

    def __init__(self, parent, label: str, var: tk.IntVar,
                 lo: int, hi: int, on_change):
        super().__init__(parent, bg=SURFACE, pady=4)
        self._var = var
        self._lo = lo
        self._hi = hi
        self._cb = on_change
        self._busy = False

        tk.Label(self, text=label, width=18, anchor="w",
                 font=("Meiryo UI", 9), fg=MUTED, bg=SURFACE).pack(side="left")

        vcmd = (self.register(lambda v: v == "" or v.lstrip("-").isdigit()), "%P")
        self._spin = tk.Spinbox(
            self, from_=lo, to=hi, textvariable=var, width=5,
            font=("Consolas", 11, "bold"), fg=ACCENT, bg=DIM,
            insertbackground=ACCENT, relief="flat", bd=0,
            buttonbackground=DIM, validate="key", validatecommand=vcmd,
            command=self._commit,
        )
        self._spin.pack(side="right", padx=(6, 0))
        tk.Label(self, text="mickey", font=("Meiryo UI", 8),
                 fg=MUTED, bg=SURFACE).pack(side="right")

        self._scale = tk.Scale(
            self, variable=var, from_=lo, to=hi,
            orient="horizontal", command=lambda _: self._on_scale(),
            bg=SURFACE, fg=TEXT, troughcolor=BG,
            highlightthickness=0, activebackground=ACCENT,
            font=("Consolas", 8), length=230, showvalue=False,
        )
        self._scale.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._spin.bind("<Return>",   lambda _: self._commit())
        self._spin.bind("<FocusOut>", lambda _: self._commit())

    def _on_scale(self):
        if not self._busy:
            self._cb()

    def _commit(self):
        try:
            v = max(self._lo, min(self._hi, int(self._spin.get())))
            self._busy = True
            self._var.set(v)
            self._busy = False
            self._cb()
        except ValueError:
            pass


class CurveCanvas(tk.Canvas):
    """スムーズカーブのプレビュー描画"""

    W, H, PAD = 320, 130, 22

    def __init__(self, parent, xs: list[float], y_vars: list[tk.DoubleVar]):
        super().__init__(parent, width=self.W, height=self.H,
                         bg=SURFACE, highlightthickness=1,
                         highlightbackground=MUTED)
        self._xs = xs
        self._yvars = y_vars
        self._y_max = 5.0

    def redraw(self) -> None:
        self.delete("all")
        w, h, p = self.W, self.H, self.PAD
        iw, ih = w - p * 2, h - p * 2
        x_max = max(self._xs) or 1.0

        def to_px(xi: float, yi: float) -> tuple[float, float]:
            return (p + xi / x_max * iw,
                    p + (1 - yi / self._y_max) * ih)

        # グリッド + Y 軸ラベル
        for yi in range(6):
            _, py = to_px(0, yi)
            self.create_line(p, py, w - p, py, fill=DIM, dash=(2, 4))
            self.create_text(p - 4, py, text=str(yi), anchor="e",
                             font=("Consolas", 7), fill=MUTED)

        # 軸
        self.create_line(p, p,     p,     h - p, fill=MUTED)
        self.create_line(p, h - p, w - p, h - p, fill=MUTED)

        # カーブ線
        pts = [to_px(self._xs[i], self._yvars[i].get()) for i in range(5)]
        for i in range(4):
            self.create_line(*pts[i], *pts[i + 1],
                             fill=ACCENT, width=2, smooth=True)

        # 制御点 + X 軸ラベル
        for i, (px, py) in enumerate(pts):
            r = 5
            color = MUTED if i == 0 else ACCENT
            self.create_oval(px - r, py - r, px + r, py + r,
                             fill=color, outline="")
            self.create_text(px, h - p + 10,
                             text=f"{self._xs[i]:.0f}",
                             font=("Consolas", 7), fill=MUTED)

        self.create_text(p - 14, p - 10, text="×",
                         font=("Consolas", 8, "bold"), fill=MUTED)
        self.create_text(w - p + 8, h - p + 10, text="spd",
                         font=("Consolas", 7), fill=MUTED)


# ═══════════════════════════════════════════════════════════════════
#  メインウィンドウ
# ═══════════════════════════════════════════════════════════════════

class MouseTuner(tk.Tk):

    PRESETS: dict[str, list[float]] = {
        "Windows既定" : [0.0, 0.75, 1.5,  2.25, 3.0 ],
        "フラット"    : [0.0, 1.0,  1.0,  1.0,  1.0 ],
        "リニア"      : [0.0, 0.5,  1.0,  1.5,  2.0 ],
        "アグレッシブ": [0.0, 1.5,  2.5,  3.5,  4.5 ],
    }

    def __init__(self):
        super().__init__()
        self.title("Mouse Tuner")
        self.resizable(False, False)
        self.configure(bg=BG)

        self._orig_speed  = get_mouse_speed()
        self._orig_params = get_mouse_params()
        self._orig_curve  = get_smooth_curve()   # (xs[5], ys[5])

        self._build_ui()
        self._load_all()

    # ─── UI 構築 ─────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # ヘッダー
        hdr = tk.Frame(self, bg=BG, pady=10)
        hdr.pack(fill="x", padx=24)
        tk.Label(hdr, text="🖱  Mouse Tuner",
                 font=("Consolas", 15, "bold"), fg=ACCENT, bg=BG).pack(side="left")
        tk.Label(hdr, text="即時反映 / 再起動不要",
                 font=("Meiryo UI", 9), fg=MUTED, bg=BG).pack(side="right")

        # タブ
        style = ttk.Style()
        style.theme_use("default")
        style.configure("MT.TNotebook", background=BG, borderwidth=0)
        style.configure("MT.TNotebook.Tab",
                         background=SURFACE, foreground=MUTED,
                         padding=[14, 6], font=("Meiryo UI", 10))
        style.map("MT.TNotebook.Tab",
                  background=[("selected", DIM)],
                  foreground=[("selected", ACCENT)])

        nb = ttk.Notebook(self, style="MT.TNotebook")
        nb.pack(fill="both", padx=16, pady=(0, 4))

        tab1 = tk.Frame(nb, bg=BG)
        tab2 = tk.Frame(nb, bg=BG)
        nb.add(tab1, text="  基本設定  ")
        nb.add(tab2, text="  スムーズカーブ  ")

        self._build_tab_basic(tab1)
        self._build_tab_curve(tab2)

        # ステータスバー
        self.status = tk.StringVar(value="読み込み中…")
        tk.Label(self, textvariable=self.status,
                 font=("Consolas", 9), fg=MUTED, bg=BG, anchor="w"
                 ).pack(fill="x", padx=24, pady=(4, 0))

        # 共通ボタン行
        brow = tk.Frame(self, bg=BG, pady=10)
        brow.pack(fill="x", padx=24)
        self._btn(brow, "↩  元に戻す", self._revert, MUTED   ).pack(side="left")
        self._btn(brow, "💾  永続保存", self._persist, "#4da6ff").pack(side="right")
        self._btn(brow, "✓  即時適用", self._apply,   ACCENT  ).pack(side="right", padx=(0, 8))

    # ── タブ1: 基本設定 ──────────────────────────────────────────

    def _build_tab_basic(self, parent: tk.Frame) -> None:
        # ポインタ速度
        c1 = self._card(parent, "ポインタ速度  (1–20)")
        row1 = tk.Frame(c1, bg=SURFACE)
        row1.pack(fill="x", padx=16, pady=10)
        self.speed_var = tk.IntVar()
        tk.Scale(
            row1, variable=self.speed_var, from_=1, to=20,
            orient="horizontal", command=lambda _: self._on_speed(),
            bg=SURFACE, fg=TEXT, troughcolor=BG,
            highlightthickness=0, activebackground=ACCENT,
            font=("Consolas", 8), length=300, showvalue=False,
        ).pack(side="left", fill="x", expand=True)
        self.speed_lbl = tk.StringVar()
        tk.Label(row1, textvariable=self.speed_lbl, width=4,
                 font=("Consolas", 14, "bold"), fg=ACCENT, bg=SURFACE).pack(side="right")

        # 加速レベル
        c2 = self._card(parent, "加速レベル")
        self.accel_var = tk.IntVar()
        for val, lbl in {
            0: "なし  (フラット)",
            1: "1段階  (Threshold1 超えで ×2)",
            2: "2段階  (Threshold2 超えでさらに ×4)",
        }.items():
            tk.Radiobutton(
                c2, text=lbl, variable=self.accel_var, value=val,
                command=self._on_params,
                bg=SURFACE, fg=TEXT, selectcolor=BG,
                activebackground=SURFACE, activeforeground=ACCENT,
                font=("Meiryo UI", 10), padx=16, pady=4,
            ).pack(anchor="w")

        # 閾値
        c3 = self._card(parent, "加速閾値  (0–200 mickey/tick)")
        tk.Label(
            c3, text="デフォルト: T1=6  T2=10     ※ 加速レベル 0 のときは無効",
            font=("Meiryo UI", 8), fg=MUTED, bg=SURFACE,
        ).pack(anchor="w", padx=16, pady=(6, 2))
        self.t1_var = tk.IntVar()
        self.t2_var = tk.IntVar()
        LinkedSliderSpin(c3, "Threshold 1  (×2)", self.t1_var,
                         0, 200, self._on_params).pack(fill="x", padx=16)
        LinkedSliderSpin(c3, "Threshold 2  (×4)", self.t2_var,
                         0, 200, self._on_params).pack(fill="x", padx=16, pady=(0, 8))

    # ── タブ2: スムーズカーブ ────────────────────────────────────

    def _build_tab_curve(self, parent: tk.Frame) -> None:
        card = self._card(parent, "スムーズカーブ  (SmoothMouseXCurve / YCurve)")

        tk.Label(
            card,
            text='「ポインターの精度を高める」の内部カーブ。加速レベル 1 以上で有効。\n'
                 'Y 軸 = 速度倍率 (0–5) 、X 軸 = 入力速度 (mickey/tick)',
            font=("Meiryo UI", 9), fg=MUTED, bg=SURFACE, justify="left",
        ).pack(anchor="w", padx=16, pady=(8, 4))

        # キャンバス
        self._curve_xs, orig_ys = self._orig_curve
        self._y_vars = [tk.DoubleVar(value=round(orig_ys[i], 2)) for i in range(5)]
        self._canvas = CurveCanvas(card, self._curve_xs, self._y_vars)
        self._canvas.pack(padx=16, pady=(4, 8))

        # 5制御点エディタ
        self._build_y_editors(card)

        # プリセット行
        prow = tk.Frame(card, bg=SURFACE)
        prow.pack(fill="x", padx=16, pady=(4, 10))
        tk.Label(prow, text="プリセット:", font=("Meiryo UI", 9),
                 fg=MUTED, bg=SURFACE).pack(side="left", padx=(0, 8))
        for name in self.PRESETS:
            self._small_btn(prow, name,
                            lambda n=name: self._apply_preset(n)).pack(side="left", padx=2)

    def _build_y_editors(self, parent: tk.Frame) -> None:
        POINT_LABELS = [
            "P0 (固定 = 0)",
            "P1 (低速域)",
            "P2 (中速域)",
            "P3 (高速域)",
            "P4 (最大速)",
        ]
        frame = tk.Frame(parent, bg=SURFACE)
        frame.pack(fill="x", padx=16, pady=2)

        for i in range(5):
            row = tk.Frame(frame, bg=SURFACE, pady=3)
            row.pack(fill="x")
            tk.Label(row, text=POINT_LABELS[i], width=18, anchor="w",
                     font=("Meiryo UI", 9), fg=MUTED, bg=SURFACE).pack(side="left")

            if i == 0:
                # P0 は常に 0 で固定
                tk.Label(row, text="0.00  (固定)",
                         font=("Consolas", 10), fg=MUTED, bg=SURFACE).pack(side="left")
                continue

            vcmd = (self.register(
                lambda v: v in ("", ".", "-") or self._is_float(v)
            ), "%P")
            sp = tk.Spinbox(
                row, from_=0.0, to=5.0, increment=0.05,
                textvariable=self._y_vars[i], format="%.2f", width=6,
                font=("Consolas", 11, "bold"), fg=ACCENT, bg=DIM,
                insertbackground=ACCENT, relief="flat", bd=0,
                buttonbackground=DIM, validate="key", validatecommand=vcmd,
                command=self._on_curve,
            )
            sp.pack(side="right", padx=(6, 0))
            sp.bind("<Return>",   lambda _, j=i: self._commit_y(j))
            sp.bind("<FocusOut>", lambda _, j=i: self._commit_y(j))

            tk.Scale(
                row, variable=self._y_vars[i],
                from_=0.0, to=5.0, resolution=0.05,
                orient="horizontal", command=lambda _: self._on_curve(),
                bg=SURFACE, fg=TEXT, troughcolor=BG,
                highlightthickness=0, activebackground=ACCENT,
                font=("Consolas", 8), length=220, showvalue=False,
            ).pack(side="left", fill="x", expand=True, padx=(0, 4))

    # ─── カード / ボタン ─────────────────────────────────────────

    def _card(self, parent: tk.Frame, title: str) -> tk.Frame:
        outer = tk.Frame(parent, bg=BG)
        outer.pack(fill="x", padx=12, pady=6)
        tk.Label(outer, text=title.upper(), font=("Consolas", 8, "bold"),
                 fg=MUTED, bg=BG).pack(anchor="w", padx=4, pady=(0, 3))
        f = tk.Frame(outer, bg=SURFACE,
                     highlightbackground=ACCENT, highlightthickness=1)
        f.pack(fill="x")
        return f

    def _btn(self, parent, text, cmd, color) -> tk.Button:
        return tk.Button(
            parent, text=text, command=cmd,
            bg=SURFACE, fg=color, activebackground=BG, activeforeground=color,
            relief="flat", bd=0, font=("Meiryo UI", 10, "bold"),
            padx=14, pady=6, cursor="hand2",
        )

    def _small_btn(self, parent, text, cmd) -> tk.Button:
        return tk.Button(
            parent, text=text, command=cmd,
            bg=DIM, fg=TEXT, activebackground=BG, activeforeground=ACCENT,
            relief="flat", bd=0, font=("Meiryo UI", 9),
            padx=8, pady=3, cursor="hand2",
        )

    # ─── イベントハンドラ ─────────────────────────────────────────

    def _load_all(self) -> None:
        self.speed_var.set(self._orig_speed)
        self.speed_lbl.set(str(self._orig_speed))
        t1, t2, accel = self._orig_params
        self.accel_var.set(accel)
        self.t1_var.set(t1)
        self.t2_var.set(t2)
        _, ys = self._orig_curve
        for i, v in enumerate(ys):
            self._y_vars[i].set(round(v, 2))
        self._canvas.redraw()
        self.status.set(
            f"現在値 ─ 速度={self._orig_speed}  加速={accel}  t1={t1} t2={t2}"
        )

    def _on_speed(self) -> None:
        v = self.speed_var.get()
        self.speed_lbl.set(str(v))
        set_mouse_speed(v)
        self.status.set(f"速度 → {v}  (即時反映)")

    def _on_params(self) -> None:
        a, t1, t2 = self.accel_var.get(), self.t1_var.get(), self.t2_var.get()
        set_mouse_params(t1, t2, a)
        self.status.set(f"加速={a}  t1={t1}  t2={t2}  (即時反映)")

    def _on_curve(self) -> None:
        self._canvas.redraw()
        ys = [self._y_vars[i].get() for i in range(5)]
        set_smooth_curve(self._curve_xs, ys)
        self.status.set(
            f"カーブ更新: [{', '.join(f'{v:.2f}' for v in ys)}]  (即時反映)"
        )

    def _commit_y(self, i: int) -> None:
        try:
            v = max(0.0, min(5.0, float(self._y_vars[i].get())))
            self._y_vars[i].set(round(v, 2))
            self._on_curve()
        except (ValueError, tk.TclError):
            pass

    def _apply_preset(self, name: str) -> None:
        for i, v in enumerate(self.PRESETS[name]):
            self._y_vars[i].set(v)
        self._on_curve()

    def _apply(self) -> None:
        self._on_speed()
        self._on_params()
        self._on_curve()
        self.status.set("✓ 適用完了")

    def _persist(self) -> None:
        set_mouse_speed(self.speed_var.get(), persist=True)
        set_mouse_params(
            self.t1_var.get(), self.t2_var.get(),
            self.accel_var.get(), persist=True,
        )
        set_smooth_curve(
            self._curve_xs,
            [self._y_vars[i].get() for i in range(5)],
            persist=True,
        )
        self.status.set("💾 Registry 保存済み（再起動後も維持）")

    def _revert(self) -> None:
        t1, t2, accel = self._orig_params
        self.speed_var.set(self._orig_speed)
        self.speed_lbl.set(str(self._orig_speed))
        self.accel_var.set(accel)
        self.t1_var.set(t1)
        self.t2_var.set(t2)
        _, ys = self._orig_curve
        for i, v in enumerate(ys):
            self._y_vars[i].set(round(v, 2))
        set_mouse_speed(self._orig_speed)
        set_mouse_params(t1, t2, accel)
        set_smooth_curve(self._curve_xs, ys)
        self._canvas.redraw()
        self.status.set("↩ 起動時の設定に戻しました")

    @staticmethod
    def _is_float(s: str) -> bool:
        try:
            float(s)
            return True
        except ValueError:
            return False


# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    MouseTuner().mainloop()
