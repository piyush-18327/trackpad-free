"""Theme, display scaling and custom widgets for the Trackpad Free window.

Plain Tk/ttk on the "clam" theme, so no packages are needed. The stock ttk
styles (TLabel, TCheckbutton, TLabelframe, TButton, ...) are themed as well,
so a page built only from standard ttk widgets matches the rest of the app.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont, ttk
import winreg

LIGHT = {
    "window": "#ffffff", "sidebar": "#f3f4f6", "sidebar_hover": "#e9ebef", "sidebar_active": "#e2e7f0",
    "text": "#1b1f24", "muted": "#5e6875", "border": "#e3e6ea",
    "field": "#ffffff", "field_border": "#c6ccd4", "code_bg": "#f6f8fa",
    "button": "#f6f7f9", "button_hover": "#eceef2", "button_pressed": "#e1e4e9",
    "accent": "#0a64d6", "accent_hover": "#0b58bb", "accent_pressed": "#0a4ea6", "accent_text": "#ffffff",
    "good": "#1a7f37", "good_bg": "#e4f4e8", "warn": "#9a5b00", "warn_bg": "#fdf1d8",
    "bad": "#c4281c", "bad_bg": "#fde7e5", "neutral": "#5e6875", "neutral_bg": "#eef0f3",
    "disabled": "#a2a9b3",
}
DARK = {
    "window": "#1e1f22", "sidebar": "#17181a", "sidebar_hover": "#23252a", "sidebar_active": "#2a2f38",
    "text": "#e8eaed", "muted": "#9aa3ad", "border": "#34373d",
    "field": "#26282c", "field_border": "#474c55", "code_bg": "#18191b",
    "button": "#2a2c31", "button_hover": "#33363c", "button_pressed": "#3c4048",
    "accent": "#4c9bff", "accent_hover": "#66aaff", "accent_pressed": "#3a87ea", "accent_text": "#0b1220",
    "good": "#5bc97a", "good_bg": "#1b3424", "warn": "#f0b54a", "warn_bg": "#3a2d12",
    "bad": "#ff7b72", "bad_bg": "#3d1d1b", "neutral": "#9aa3ad", "neutral_bg": "#2b2e33",
    "disabled": "#6b727c",
}

# Segoe Fluent Icons / Segoe MDL2 Assets code points for the sidebar.
NAV_ICONS = {
    "my trackpad": "", "click & precision": "", "driver setup": "",
    "diagnostics": "", "gestures": "",
}
DEFAULT_NAV_ICON = ""
_scale = 1.0


def px(value: float) -> int:
    """Convert a 96-DPI design size to physical pixels for this display."""
    return round(value * _scale)


def enable_dpi_awareness() -> None:
    """Render text crisply on scaled displays; must run before the Tk root exists."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor aware
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def prefers_dark() -> bool:
    choice = os.environ.get("TRACKPADFREE_THEME", "").lower()
    if choice in ("dark", "light"):
        return choice == "dark"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def battery_kind(level: int | None, low: int = 20) -> str:
    """Status color for a battery level; thresholds match the tray icon."""
    if level is None:
        return "neutral"
    return "bad" if level <= low else "warn" if level < 50 else "good"


def load_icons(root: tk.Misc, folder: Path) -> dict[int, tk.PhotoImage]:
    """Pre-rendered app icons from assets/ (see tools/make_icons.py), keyed by size."""
    icons = {}
    for path in folder.glob("icon-*.png"):
        try:
            icons[int(path.stem.split("-")[1])] = tk.PhotoImage(master=root, file=str(path))
        except (ValueError, tk.TclError):
            continue
    return icons


def round_rect(canvas: tk.Canvas, x0: float, y0: float, x1: float, y1: float, radius: float, **options) -> int:
    radius = max(0.0, min(radius, (x1 - x0) / 2, (y1 - y0) / 2))
    points = [x0 + radius, y0, x1 - radius, y0, x1, y0, x1, y0 + radius, x1, y1 - radius, x1, y1,
              x1 - radius, y1, x0 + radius, y1, x0, y1, x0, y1 - radius, x0, y0 + radius, x0, y0]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **options)


class Theme:
    def __init__(self, root: tk.Tk, dark: bool | None = None) -> None:
        global _scale
        _scale = root.winfo_fpixels("1i") / 96
        self.dark = prefers_dark() if dark is None else dark
        self.c = DARK if self.dark else LIGHT
        families = set(tkfont.families(root))

        def pick(*names: str) -> str:
            return next((name for name in names if name in families), "")

        self.text_family = pick("Segoe UI Variable Text", "Segoe UI") or "TkDefaultFont"
        self.display_family = pick("Segoe UI Variable Display", "Segoe UI Semibold", "Segoe UI") or self.text_family
        self.icon_family = pick("Segoe Fluent Icons", "Segoe MDL2 Assets")
        self.mono_family = pick("Cascadia Mono", "Consolas") or "TkFixedFont"
        self._configure(root)

    def font(self, size: int, weight: str = "normal", display: bool = False) -> tuple:
        return (self.display_family if display else self.text_family, size, weight)

    def _configure(self, root: tk.Tk) -> None:
        c, style = self.c, ttk.Style(root)
        root.configure(background=c["window"])
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkCaptionFont"):
            tkfont.nametofont(name).configure(family=self.text_family, size=10)
        tkfont.nametofont("TkFixedFont").configure(family=self.mono_family, size=9)
        for option, value in (("background", c["field"]), ("foreground", c["text"]), ("selectBackground", c["accent"]),
                              ("selectForeground", c["accent_text"]), ("borderWidth", 0)):
            root.option_add(f"*TCombobox*Listbox.{option}", value)

        style.theme_use("clam")
        style.configure(".", background=c["window"], foreground=c["text"], font=self.font(10),
                        bordercolor=c["border"], lightcolor=c["window"], darkcolor=c["window"],
                        troughcolor=c["neutral_bg"], focuscolor=c["accent"], fieldbackground=c["field"],
                        selectbackground=c["accent"], selectforeground=c["accent_text"],
                        insertcolor=c["text"], arrowcolor=c["muted"])
        style.map(".", foreground=[("disabled", c["disabled"])])

        # Text styles. Heading/Muted/Battery/Title keep the names app.py already used.
        style.configure("TLabel", background=c["window"], foreground=c["text"])
        style.configure("Muted.TLabel", foreground=c["muted"])
        style.configure("Small.TLabel", foreground=c["muted"], font=self.font(9))
        style.configure("Strong.TLabel", font=self.font(10, "bold"))
        style.configure("Title.TLabel", font=self.font(20, "bold", display=True))
        style.configure("Hero.TLabel", font=self.font(17, "bold", display=True))
        style.configure("Heading.TLabel", font=self.font(12, "bold", display=True))
        style.configure("Battery.TLabel", font=self.font(30, "bold", display=True))
        style.configure("Step.TLabel", background=c["accent"], foreground=c["accent_text"],
                        font=self.font(9, "bold"), padding=(px(6), px(2)), width=2, anchor="center")
        for kind in ("good", "warn", "bad", "neutral"):
            style.configure(f"{kind.title()}.Pill.TLabel", background=c[f"{kind}_bg"], foreground=c[kind],
                            font=self.font(9, "bold"), padding=(px(10), px(3)))

        # Containers: cards and label frames are bordered panels on the window color.
        style.configure("TFrame", background=c["window"])
        for name in ("Card.TFrame", "TLabelframe"):
            style.configure(name, background=c["window"], bordercolor=c["border"], lightcolor=c["border"],
                            darkcolor=c["border"], relief="solid", borderwidth=1)
        style.configure("TLabelframe", padding=px(16))
        style.configure("TLabelframe.Label", background=c["window"], foreground=c["text"], font=self.font(11, "bold", display=True))
        style.configure("TSeparator", background=c["border"])
        style.configure("Sidebar.TFrame", background=c["sidebar"])
        style.configure("Sidebar.TLabel", background=c["sidebar"], foreground=c["text"])
        style.configure("SidebarMuted.TLabel", background=c["sidebar"], foreground=c["muted"], font=self.font(9))
        style.configure("Brand.TLabel", background=c["sidebar"], foreground=c["text"], font=self.font(13, "bold", display=True))

        # Buttons: quiet secondary buttons plus a filled accent for the main action.
        flat = {"relief": "flat", "padding": (px(14), px(6)), "focusthickness": 1}
        style.configure("TButton", background=c["button"], foreground=c["text"], bordercolor=c["field_border"],
                        lightcolor=c["button"], darkcolor=c["button"], **flat)
        style.map("TButton",
                  background=[("disabled", c["button"]), ("pressed", c["button_pressed"]), ("active", c["button_hover"])],
                  lightcolor=[("disabled", c["button"]), ("pressed", c["button_pressed"]), ("active", c["button_hover"])],
                  darkcolor=[("disabled", c["button"]), ("pressed", c["button_pressed"]), ("active", c["button_hover"])],
                  bordercolor=[("disabled", c["border"])], foreground=[("disabled", c["disabled"])])
        style.configure("Accent.TButton", background=c["accent"], foreground=c["accent_text"], bordercolor=c["accent"],
                        lightcolor=c["accent"], darkcolor=c["accent"], font=self.font(10, "bold"), **flat)
        accent_states = [("disabled", c["neutral_bg"]), ("pressed", c["accent_pressed"]), ("active", c["accent_hover"])]
        style.map("Accent.TButton", background=accent_states, lightcolor=accent_states, darkcolor=accent_states,
                  bordercolor=accent_states, foreground=[("disabled", c["disabled"])])

        style.configure("Link.TButton", background=c["window"], foreground=c["accent"], bordercolor=c["window"],
                        lightcolor=c["window"], darkcolor=c["window"], relief="flat", padding=(px(8), px(6)), focusthickness=1)
        style.map("Link.TButton", background=[("active", c["window"]), ("pressed", c["window"])],
                  lightcolor=[("active", c["window"])], darkcolor=[("active", c["window"])],
                  foreground=[("disabled", c["disabled"]), ("pressed", c["accent_pressed"]), ("active", c["accent_hover"])])

        # Fluent-style check boxes and radio buttons drawn as images.
        self._images: list[tk.PhotoImage] = []
        for name, shape in (("Checkbutton", "box"), ("Radiobutton", "circle")):
            off = self._indicator(root, shape, c["field"], c["field_border"])
            hover = self._indicator(root, shape, c["field"], c["muted"])
            on = self._indicator(root, shape, c["accent"], c["accent"], c["accent_text"])
            disabled_off = self._indicator(root, shape, c["neutral_bg"], c["border"])
            disabled_on = self._indicator(root, shape, c["disabled"], c["disabled"], c["field"])
            element = f"Fluent.{name}.indicator"
            try:
                style.element_create(element, "image", off, ("disabled", "selected", disabled_on), ("disabled", disabled_off),
                                     ("selected", on), ("active", hover), sticky="w")
            except tk.TclError:
                pass  # already created in this interpreter
            style.layout(f"T{name}", [(f"{name}.padding", {"sticky": "nswe", "children": [
                (element, {"side": "left", "sticky": ""}),
                (f"{name}.focus", {"side": "left", "sticky": "w", "children": [(f"{name}.label", {"sticky": "nswe"})]}),
            ]})])
            style.configure(f"T{name}", background=c["window"], foreground=c["text"], padding=(0, px(3)), focuscolor=c["accent"])
            style.map(f"T{name}", background=[("active", c["window"])], foreground=[("disabled", c["disabled"])])

        for name in ("TCombobox", "TSpinbox", "TEntry"):
            style.configure(name, fieldbackground=c["field"], background=c["button"], foreground=c["text"],
                            bordercolor=c["field_border"], lightcolor=c["field"], darkcolor=c["field"],
                            arrowcolor=c["muted"], padding=px(5), insertcolor=c["text"])
            style.map(name, fieldbackground=[("disabled", c["neutral_bg"]), ("readonly", c["field"])],
                      bordercolor=[("focus", c["accent"])], background=[("active", c["button_hover"])],
                      selectbackground=[("readonly", c["field"])], selectforeground=[("readonly", c["text"])],
                      foreground=[("disabled", c["disabled"])])

        style.configure("Vertical.TScrollbar", background=c["button"], troughcolor=c["window"], bordercolor=c["window"],
                        lightcolor=c["button"], darkcolor=c["button"], arrowcolor=c["muted"], gripcount=0)
        style.map("Vertical.TScrollbar", background=[("active", c["button_hover"])])
        style.configure("Busy.Horizontal.TProgressbar", background=c["accent"], troughcolor=c["neutral_bg"],
                        bordercolor=c["window"], lightcolor=c["accent"], darkcolor=c["accent"])

    def _indicator(self, root: tk.Tk, shape: str, fill: str, border: str, mark: str | None = None) -> tk.PhotoImage:
        """Anti-aliased check box or radio indicator, blended onto the window color, with a gap on the right."""
        size, gap, samples = px(18), px(9), 4
        stroke = max(1.0, size * 0.075)
        background = self.c["window"]
        rgb = [tuple(int(color[i:i + 2], 16) for i in (1, 3, 5)) for color in (background, border, fill, mark or fill)]

        def inside(u: float, v: float, inset: float) -> bool:
            if shape == "circle":
                return (u - size / 2) ** 2 + (v - size / 2) ** 2 <= (size / 2 - inset) ** 2
            radius = max(size * 0.22 - inset, 0.5)
            low, high = inset, size - inset
            dx = max(low + radius - u, 0.0, u - (high - radius))
            dy = max(low + radius - v, 0.0, v - (high - radius))
            return low <= u <= high and low <= v <= high and dx * dx + dy * dy <= radius * radius

        def on_mark(u: float, v: float) -> bool:
            if mark is None:
                return False
            if shape == "circle":
                return (u - size / 2) ** 2 + (v - size / 2) ** 2 <= (size * 0.2) ** 2
            points = [(0.26 * size, 0.52 * size), (0.43 * size, 0.69 * size), (0.75 * size, 0.33 * size)]
            for (ax, ay), (bx, by) in zip(points, points[1:]):
                t = max(0.0, min(1.0, ((u - ax) * (bx - ax) + (v - ay) * (by - ay)) / ((bx - ax) ** 2 + (by - ay) ** 2)))
                if (u - ax - t * (bx - ax)) ** 2 + (v - ay - t * (by - ay)) ** 2 <= (size * 0.065) ** 2:
                    return True
            return False

        image = tk.PhotoImage(master=root, width=size + gap, height=size)
        transparent = []
        for y in range(size):
            row = []
            for x in range(size + gap):
                outer = inner = marked = 0
                if x < size:
                    for sy in range(samples):
                        for sx in range(samples):
                            u, v = x + (sx + 0.5) / samples, y + (sy + 0.5) / samples
                            outer += inside(u, v, 0.5)
                            inner += inside(u, v, 0.5 + stroke)
                            marked += on_mark(u, v)
                total = samples * samples
                color = rgb[0]
                for layer, amount in ((rgb[1], outer), (rgb[2], inner), (rgb[3], marked)):
                    color = tuple(a + (b - a) * amount / total for a, b in zip(color, layer))
                row.append("#%02x%02x%02x" % tuple(round(channel) for channel in color))
                if outer == 0:
                    transparent.append((x, y))
            image.put("{" + " ".join(row) + "}", to=(0, y))
        for x, y in transparent:  # PhotoImage.transparency_set needs Python 3.13+, so call Tk directly
            image.tk.call(image.name, "transparency", "set", x, y, True)
        self._images.append(image)
        return image

    def style_titlebar(self, root: tk.Tk) -> None:
        """Match the Windows 11 title bar to the sidebar (dark mode aware)."""
        try:
            root.update_idletasks()
            user32, dwm = ctypes.WinDLL("user32"), ctypes.WinDLL("dwmapi")
            user32.GetParent.argtypes, user32.GetParent.restype = [wintypes.HWND], wintypes.HWND
            dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
            hwnd = user32.GetParent(root.winfo_id())
            dark = ctypes.c_int(int(self.dark))
            dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), 4)  # DWMWA_USE_IMMERSIVE_DARK_MODE
            red, green, blue = (int(self.c["sidebar"][i:i + 2], 16) for i in (1, 3, 5))
            caption = wintypes.DWORD(red | green << 8 | blue << 16)
            dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), 4)  # DWMWA_CAPTION_COLOR (Windows 11)
        except (AttributeError, OSError):
            pass  # cosmetic only


class WrapLabel(ttk.Label):
    """A label that wraps its text to whatever width the layout gives it (pack with fill="x")."""

    def __init__(self, master: tk.Misc, **options) -> None:
        super().__init__(master, **options)
        self.bind("<Configure>", lambda event: self.configure(wraplength=max(event.width - 2, 40)), add="+")


class Card(ttk.Frame):
    """Bordered panel with an optional title and subtitle; pack content into it."""

    def __init__(self, master: tk.Misc, title: str | None = None, subtitle: str | None = None, **options) -> None:
        options.setdefault("padding", px(18))
        super().__init__(master, style="Card.TFrame", **options)
        if title:
            ttk.Label(self, text=title, style="Heading.TLabel").pack(anchor="w")
        if subtitle:
            WrapLabel(self, text=subtitle, style="Muted.TLabel").pack(fill="x", pady=(px(4), 0))


def set_pill(label: ttk.Label, kind: str, text: str) -> None:
    label.configure(style=f"{kind.title()}.Pill.TLabel", text=text)


class BatteryGauge(tk.Canvas):
    """Battery outline filled to the current level in the status color."""

    def __init__(self, master: tk.Misc, theme: Theme, width: int = 132, height: int = 56) -> None:
        super().__init__(master, width=px(width), height=px(height), background=theme.c["window"],
                         highlightthickness=0, borderwidth=0)
        self.theme, self.level, self.low = theme, None, 20
        self.bind("<Configure>", lambda _event: self._draw())

    def set(self, level: int | None, low: int = 20) -> None:
        self.level, self.low = level, low
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        c = self.theme.c
        width = max(self.winfo_width(), int(self["width"]))
        height = max(self.winfo_height(), int(self["height"]))
        stroke, nub = max(2, px(2.5)), px(6)
        x0, y0, x1, y1 = stroke, stroke, width - nub - px(3), height - stroke
        round_rect(self, x0, y0, x1, y1, px(11), outline=c["field_border"], fill="", width=stroke)
        round_rect(self, x1 + px(2), height * 0.34, x1 + px(2) + nub, height * 0.66, px(2), fill=c["field_border"], outline="")
        if self.level is None:
            return
        inset = stroke + px(3)
        inner = (x1 - x0 - 2 * inset) * max(0, min(self.level, 100)) / 100
        if inner > 0:
            round_rect(self, x0 + inset, y0 + inset, x0 + inset + max(inner, px(4)), y1 - inset, px(7),
                       fill=c[battery_kind(self.level, self.low)], outline="")


class _NavItem(tk.Frame):
    def __init__(self, master: tk.Misc, theme: Theme, icon: str, text: str, command) -> None:
        c = theme.c
        super().__init__(master, background=c["sidebar"], cursor="hand2", takefocus=1, highlightthickness=1,
                         highlightbackground=c["sidebar"], highlightcolor=c["accent"])
        self.theme, self.active, self.command = theme, False, command
        self.indicator = tk.Frame(self, width=px(3), background=c["sidebar"])
        self.indicator.pack(side="left", fill="y", pady=px(9))
        parts = [self, self.indicator]
        if theme.icon_family:
            self.icon = tk.Label(self, text=icon, font=(theme.icon_family, 12), background=c["sidebar"], foreground=c["text"])
            self.icon.pack(side="left", padx=(px(10), 0), pady=px(8))
            parts.append(self.icon)
        self.label = tk.Label(self, text=text, anchor="w", font=theme.font(10), background=c["sidebar"], foreground=c["text"])
        self.label.pack(side="left", fill="x", expand=True, padx=px(12), pady=px(8))
        parts.append(self.label)
        for widget in parts:
            widget.bind("<Button-1>", lambda _event: command())
            widget.bind("<Enter>", lambda _event: self._paint(hover=True))
            widget.bind("<Leave>", self._leave)
        self.bind("<Return>", lambda _event: command())
        self.bind("<space>", lambda _event: command())

    def _leave(self, event: tk.Event) -> None:
        inside = self.winfo_containing(event.x_root, event.y_root)
        if inside is None or not str(inside).startswith(str(self)):
            self._paint(hover=False)

    def set_active(self, active: bool) -> None:
        self.active = active
        self._paint(hover=False)

    def _paint(self, hover: bool) -> None:
        c = self.theme.c
        background = c["sidebar_active"] if self.active else c["sidebar_hover"] if hover else c["sidebar"]
        for widget in self.winfo_children() + [self]:
            widget.configure(background=background)
        self.configure(highlightbackground=c["sidebar"])
        self.indicator.configure(background=c["accent"] if self.active else background)
        self.label.configure(font=self.theme.font(10, "bold" if self.active else "normal"))


class NavBook(ttk.Frame):
    """Sidebar navigation with a ttk.Notebook-style API.

    Create pages as children of this widget, then ``add(page, text=...)`` and
    ``select(page)`` exactly as with ttk.Notebook. Pages scroll when taller
    than the window; ``footer`` and ``sidebar_footer`` are free for the app.
    """

    def __init__(self, master: tk.Misc, theme: Theme, brand_icon: tk.PhotoImage | None = None,
                 version: str = "") -> None:
        super().__init__(master)
        self.theme, self._pages, self._current = theme, [], None
        self.columnconfigure(1, weight=1)
        self.columnconfigure(0, minsize=px(236))
        self.rowconfigure(0, weight=1)

        self.sidebar = ttk.Frame(self, style="Sidebar.TFrame", padding=(px(10), px(18), px(10), px(14)))
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        brand = ttk.Frame(self.sidebar, style="Sidebar.TFrame", padding=(px(8), 0, 0, px(18)))
        brand.pack(fill="x")
        if brand_icon is not None:
            ttk.Label(brand, image=brand_icon, style="Sidebar.TLabel").pack(side="left", padx=(0, px(10)))
        names = ttk.Frame(brand, style="Sidebar.TFrame")
        names.pack(side="left")
        ttk.Label(names, text="Trackpad Free", style="Brand.TLabel").pack(anchor="w")
        ttk.Label(names, text=f"Magic Trackpad for Windows{'  ·  v' + version if version else ''}",
                  style="SidebarMuted.TLabel").pack(anchor="w")
        self.nav = ttk.Frame(self.sidebar, style="Sidebar.TFrame")
        self.nav.pack(fill="x")
        self.sidebar_footer = ttk.Frame(self.sidebar, style="Sidebar.TFrame", padding=(px(8), 0))
        self.sidebar_footer.pack(side="bottom", fill="x")

        content = ttk.Frame(self)
        content.grid(row=0, column=1, sticky="nsew")
        self.title = ttk.Label(content, style="Title.TLabel")
        self.title.pack(anchor="w", padx=px(32), pady=(px(22), 0))
        self.subtitle = WrapLabel(content, style="Muted.TLabel")
        self.subtitle.pack(fill="x", padx=px(32), pady=(px(2), px(14)))
        self.footer = ttk.Frame(content, padding=(px(32), px(10)))
        self.footer.pack(side="bottom", fill="x")
        ttk.Separator(content).pack(side="bottom", fill="x")
        viewport = ttk.Frame(content)
        viewport.pack(fill="both", expand=True)
        viewport.rowconfigure(0, weight=1)
        viewport.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(viewport, background=theme.c["window"], highlightthickness=0, borderwidth=0, yscrollincrement=1)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = ttk.Scrollbar(viewport, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self._window = self.canvas.create_window(0, 0, anchor="nw")
        self.canvas.bind("<Configure>", self._resize)
        self.bind_all("<MouseWheel>", self._on_wheel, add="+")

    # ttk.Notebook-compatible API -------------------------------------------------
    def add(self, page: tk.Misc, text: str = "", subtitle: str = "", **_options) -> None:
        if isinstance(page, ttk.Frame):
            page.configure(padding=(px(32), 0, px(32), px(28)))
        icon = NAV_ICONS.get(text.lower(), DEFAULT_NAV_ICON)
        item = _NavItem(self.nav, self.theme, icon, text, lambda: self.select(page))
        item.pack(fill="x", pady=px(1))
        self._pages.append({"page": page, "text": text, "subtitle": subtitle, "item": item})
        page.bind("<Configure>", lambda _event: self._update_scroll(), add="+")
        if self._current is None:
            self.select(page)

    def select(self, page: tk.Misc | None = None) -> str:
        if page is None:
            return str(self._current) if self._current is not None else ""
        if isinstance(page, str):
            page = self.nametowidget(page)
        entry = next(entry for entry in self._pages if entry["page"] is page)
        for other in self._pages:
            other["item"].set_active(other is entry)
        self.canvas.itemconfigure(self._window, window=page)
        self.title.configure(text=entry["text"])
        self.subtitle.configure(text=entry["subtitle"])
        if entry["subtitle"]:
            self.subtitle.pack_configure(pady=(px(2), px(14)))
        else:
            self.subtitle.pack_configure(pady=(0, px(10)))
        self._current = page
        self.canvas.yview_moveto(0)
        self.after_idle(self._update_scroll)
        return str(page)

    def tabs(self) -> list[str]:
        return [str(entry["page"]) for entry in self._pages]

    def tab(self, page: tk.Misc, option: str | None = None, **options):
        entry = next(entry for entry in self._pages if entry["page"] is page)
        if "text" in options:
            entry["text"] = options["text"]
            entry["item"].label.configure(text=options["text"])
        return entry.get(option) if option else {"text": entry["text"]}

    # Scrolling -----------------------------------------------------------------
    def _resize(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)
        self._update_scroll()

    def _update_scroll(self) -> None:
        if self._current is None:
            return
        height = self._current.winfo_reqheight()
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), height))
        if height > self.canvas.winfo_height() + 1:
            self.scrollbar.grid(row=0, column=1, sticky="ns")
        else:
            self.scrollbar.grid_remove()
            self.canvas.yview_moveto(0)

    def _on_wheel(self, event: tk.Event) -> None:
        widget = event.widget
        if not isinstance(widget, tk.Misc) or not self.scrollbar.winfo_ismapped():
            return
        if widget.winfo_class() in ("Text", "Listbox", "TCombobox", "TSpinbox", "Treeview"):
            return  # these scroll themselves
        if not str(widget).startswith(str(self)) or str(widget).startswith(str(self.sidebar)):
            return
        # Precision touchpads send small deltas; scroll by pixels for smooth movement.
        self.canvas.yview_scroll(round(-event.delta / 2), "units")
