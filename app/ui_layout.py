"""Width-aware Tk adapters with display-independent layout calculations."""

from tkinter import ttk


def wrap_width(width, padding=0):
    return max(1, int(width) - int(padding))


def pane_split(width, left_weight, right_weight):
    return max(1, int(width * left_weight / (left_weight + right_weight)))


def initial_pane_split(paned, left_weight, right_weight):
    def mapped(event=None):
        if event is not None and event.widget is not paned:
            return
        if getattr(paned, "_initial_split_done", False) or paned.winfo_width() <= 1:
            return
        paned._initial_split_done = True
        paned.sashpos(0, pane_split(paned.winfo_width(), left_weight, right_weight))

    paned.bind("<Map>", mapped, add="+")


def flow_rows(width, widths, gap=0):
    rows = []
    used = 0
    for index, item_width in enumerate(widths):
        spacing = gap if rows and rows[-1] else 0
        if not rows or (rows[-1] and used + spacing + item_width > width):
            rows.append([])
            used = 0
            spacing = 0
        rows[-1].append(index)
        used += spacing + item_width
    return rows


# 折り返しの幅の小さな変化は無視する。ラベルの幅で親の幅が決まる所（大きさが中身で決まる窓など）では、
# 「折り返しを狭める → 親が縮む → さらに狭める」が止まらなくなる（閉じるときの確認の窓で、画面が固まった）。
WRAP_HYSTERESIS = 8
MIN_WRAP = 120
DIALOG_INITIAL_WRAP = 420


def next_wraplength(current, width, padding=4, hysteresis=WRAP_HYSTERESIS, minimum=MIN_WRAP):
    """新しい折り返しの幅。変える必要が無ければ None。"""
    length = max(minimum, wrap_width(width, padding))
    if abs(int(current) - length) <= hysteresis:
        return None
    return length


def _autowrap(label, container=None, padding=4):
    container = container or label.master

    def update(event=None):
        if not label.winfo_exists():
            return
        width = label.winfo_width()
        if width <= 1:
            width = container.winfo_width()
        if width <= 1:
            return
        length = next_wraplength(label.cget("wraplength"), width, padding)
        if length is None:
            return
        history = getattr(label, "_wrap_history", [])
        # A → B → A と行ったり来たりするとき（ラベルの幅で親の幅が決まる所）は、戻さずに止める
        if len(history) >= 2 and history[-2] == length:
            return
        label._wrap_history = (history + [length])[-4:]
        label.configure(wraplength=length)

    label.bind("<Configure>", update, add="+")
    container.bind("<Configure>", update, add="+")
    label.bind("<Map>", update, add="+")
    return label


class WrappingLabel(ttk.Label):
    def __init__(self, parent, **options):
        options.setdefault("justify", "left")
        options.setdefault("anchor", "w")
        initial = options.pop("wraplength", None)
        if initial is None:
            # 窓（Toplevel）の中の文は、窓の幅が中身で決まるので、読みやすい幅から始める
            try:
                in_dialog = parent.winfo_toplevel() is not parent._root()
            except Exception:
                in_dialog = False
            initial = DIALOG_INITIAL_WRAP if in_dialog else 100
        else:
            in_dialog = False
        super().__init__(parent, wraplength=initial, **options)
        # 窓（Toplevel）は中身で幅が決まるので、自動の折り返しはしない（固定の幅で折り返す）
        if not in_dialog:
            _autowrap(self)

    def pack(self, **options):
        options["fill"] = "x"
        return super().pack(**options)

    def grid(self, **options):
        options["sticky"] = "ew"
        return super().grid(**options)


class WrappingCheck(ttk.Frame):
    def __init__(self, parent, text, variable, command=None, **options):
        super().__init__(parent)
        self.check = ttk.Checkbutton(self, text="", variable=variable, command=command, **options)
        self.check.grid(row=0, column=0, sticky="nw")
        self.label = WrappingLabel(self, text=text)
        self.label.grid(row=0, column=1, sticky="ew")
        self.columnconfigure(1, weight=1)
        self.label.bind("<Button-1>", self._toggle)

    def _toggle(self, event=None):
        self.check.invoke()
        return "break"

    def pack(self, **options):
        options["fill"] = "x"
        return super().pack(**options)

    def grid(self, **options):
        options["sticky"] = "ew"
        return super().grid(**options)


def _wrapping_check(parent, text, variable, command=None, **options):
    return WrappingCheck(parent, text, variable, command, **options)


class FlowRow(ttk.Frame):
    def __init__(self, parent, **options):
        super().__init__(parent, width=1, **options)
        self._items = []
        self._fills = {}
        self._layout_pending = None
        self.bind("<Configure>", self.request_layout, add="+")
        self.bind("<Map>", self.request_layout, add="+")
        self.bind("<<ThemeChanged>>", self.request_layout, add="+")

    def add(self, widget, side="left", padx=0, **options):
        if isinstance(padx, (tuple, list)):
            before, after = padx
        else:
            before = after = padx
        self._items.append((widget, side, before, after))
        self._fills[widget] = options.get("fill")
        widget.bind("<Configure>", self.request_layout, add="+")
        widget.bind("<<ThemeChanged>>", self.request_layout, add="+")
        self.request_layout()
        return widget

    def request_layout(self, event=None):
        if self._layout_pending is None:
            self._layout_pending = self.after_idle(self._layout)

    def _layout(self):
        self._layout_pending = None
        items = [item for item in self._items if item[1] != "right"]
        items += [item for item in reversed(self._items) if item[1] == "right"]
        items = [item for item in items if item[0].winfo_exists()]
        widths = [widget.winfo_reqwidth() + before + after for widget, _, before, after in items]
        available = self.winfo_width()
        # 置き直すとボタンに <Configure> が来て、また並べ直しを頼む。幅とボタンの大きさが前と同じなら何もしない
        # （しないと並べ直しが止まらず、画面が固まる。v0.13.0 候補で起きた）。
        signature = (available, tuple(widths), tuple(widget.winfo_reqheight() for widget, *_ in items))
        if signature == getattr(self, "_last_signature", None):
            return
        self._last_signature = signature
        top = 0
        for row in flow_rows(available, widths):
            row_height = max(items[index][0].winfo_reqheight() for index in row)
            row_width = sum(widths[index] for index in row)
            right_width = sum(widths[index] for index in row if items[index][1] == "right")
            left = 0
            for index in row:
                widget, side, before, after = items[index]
                if side == "right" and right_width:
                    left += max(0, available - row_width)
                    right_width = 0
                placement = {"x": left + before, "y": top + (row_height - widget.winfo_reqheight()) // 2}
                if getattr(self, "_fills", {}).get(widget) in ("y", "both"):
                    placement.update(y=top, height=row_height)
                widget.place(**placement)
                left += widths[index]
            top += row_height + 4
        height = max(1, top - 4)
        if self.winfo_reqheight() != height:
            self.configure(height=height)

    def destroy(self):
        if self._layout_pending is not None:
            self.after_cancel(self._layout_pending)
        super().destroy()
