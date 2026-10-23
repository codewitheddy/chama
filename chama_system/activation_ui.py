"""
Activation window — Finance Wise TBM.
Styled to match the app's dark sidebar theme.
Buttons are anchored to the bottom so they're always visible regardless of DPI.
"""

import tkinter as tk


# ── Theme colours ─────────────────────────────────────────────────
BG       = "#1e2a3a"
BG_CARD  = "#0f1923"
DIVIDER  = "#2c3e52"
TXT_H    = "#f1f5f9"
TXT_M    = "#94a3b8"
TXT_D    = "#64748b"
ACCENT   = "#2563eb"
ACCENT_H = "#1d4ed8"
GREEN    = "#16a34a"
GREEN_H  = "#15803d"
MID_BLUE = "#38bdf8"
RED      = "#ef4444"


def _hover(btn, normal, over):
    btn.bind("<Enter>", lambda _: btn.config(bg=over))
    btn.bind("<Leave>", lambda _: btn.config(bg=normal))


def show_activation_window(machine_id: str) -> bool:
    activated = [False]

    root = tk.Tk()
    root.title("Finance Wise TBM — Activation")
    root.resizable(False, False)
    root.configure(bg=BG)

    # ── Tell Windows this process is DPI-aware so geometry is in real pixels ──
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    W, H = 560, 620
    root.update_idletasks()
    sx, sy = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{W}x{H}+{(sx - W) // 2}+{(sy - H) // 2}")
    root.minsize(W, H)

    # ════════════════════════════════════════════════════════════════
    # BOTTOM BAR — packed first so it's always visible
    # ════════════════════════════════════════════════════════════════
    bottom = tk.Frame(root, bg=BG)
    bottom.pack(side="bottom", fill="x", padx=32, pady=(0, 24))

    # Error label sits just above the buttons
    error_lbl = tk.Label(bottom, text="", bg=BG, fg=RED,
                         font=("Segoe UI", 9), anchor="w")
    error_lbl.pack(fill="x", pady=(0, 10))

    btn_row = tk.Frame(bottom, bg=BG)
    btn_row.pack(fill="x")
    btn_row.columnconfigure(0, weight=3)
    btn_row.columnconfigure(1, weight=1)

    from licensing import load_key
    initial_key = load_key()
    key_var       = tk.StringVar(value=initial_key)
    key_underline = None   # assigned later

    def _activate():
        from licensing import verify_key, save_key
        key = key_var.get().strip().upper()
        error_lbl.config(text="")
        if key_underline:
            key_underline.config(bg=ACCENT)

        if not key:
            error_lbl.config(text="⚠  Please enter your activation key.")
            if key_underline:
                key_underline.config(bg=RED)
            return

        if verify_key(machine_id, key):
            try:
                save_key(key)
                activated[0] = True
                act_btn.config(text="  ✓  Activated!", bg=GREEN)
                root.after(700, root.destroy)
            except Exception as e:
                error_lbl.config(text=f"⚠  Failed to save key: {e}")
                if key_underline:
                    key_underline.config(bg=RED)
        else:
            error_lbl.config(text="⚠  Invalid key — please check and try again.")
            if key_underline:
                key_underline.config(bg=RED)
            root.after(2800, lambda: (
                error_lbl.config(text=""),
                key_underline.config(bg=ACCENT) if key_underline else None,
            ))

    def _cancel():
        activated[0] = False
        root.destroy()

    act_btn = tk.Button(
        btn_row, text="    Activate Now    ",
        command=_activate,
        bg=GREEN, fg="white",
        activebackground=GREEN_H, activeforeground="white",
        relief="raised", bd=2, cursor="hand2",
        font=("Segoe UI", 11, "bold"), pady=11,
    )
    act_btn.grid(row=0, column=0, sticky="ew", padx=(0, 10))
    _hover(act_btn, GREEN, GREEN_H)

    exit_btn = tk.Button(
        btn_row, text="  Exit  ",
        command=_cancel,
        bg=DIVIDER, fg=TXT_H,
        activebackground="#3d5166", activeforeground=TXT_H,
        relief="raised", bd=2, cursor="hand2",
        font=("Segoe UI", 11), pady=11,
    )
    exit_btn.grid(row=0, column=1, sticky="ew")
    _hover(exit_btn, DIVIDER, "#3d5166")

    # Footer note
    tk.Label(
        bottom,
        text="Licensed per machine. Copying to another PC requires a new key.",
        bg=BG, fg=TXT_D, font=("Segoe UI", 7),
    ).pack(pady=(12, 0))

    # ════════════════════════════════════════════════════════════════
    # TOP ACCENT BAR
    # ════════════════════════════════════════════════════════════════
    tk.Frame(root, bg=ACCENT, height=4).pack(side="top", fill="x")

    # ════════════════════════════════════════════════════════════════
    # SCROLLABLE CONTENT AREA (handles any DPI overflow gracefully)
    # ════════════════════════════════════════════════════════════════
    canvas = tk.Canvas(root, bg=BG, bd=0, highlightthickness=0)
    canvas.pack(side="top", fill="both", expand=True)

    content = tk.Frame(canvas, bg=BG)
    canvas.create_window((0, 0), window=content, anchor="nw")

    def _on_resize(event):
        canvas.itemconfig("all", width=event.width)
    canvas.bind("<Configure>", _on_resize)

    content.bind("<Configure>",
                 lambda e: canvas.config(scrollregion=canvas.bbox("all")))

    P = 32   # horizontal padding for all content rows

    # ── Header ────────────────────────────────────────────────────
    hdr = tk.Frame(content, bg=BG)
    hdr.pack(fill="x", padx=P, pady=(24, 0))

    tk.Label(hdr, text="🏦", bg=BG, fg=TXT_H,
             font=("Segoe UI Emoji", 28)).pack(side="left", padx=(0, 16))

    title_col = tk.Frame(hdr, bg=BG)
    title_col.pack(side="left", fill="x", expand=True)

    tk.Label(title_col, text="Finance Wise TBM",
             bg=BG, fg=TXT_H, font=("Segoe UI", 17, "bold"),
             anchor="w").pack(fill="x")
    tk.Label(title_col, text="Activation Required",
             bg=BG, fg=TXT_M, font=("Segoe UI", 10),
             anchor="w").pack(fill="x")

    # ── Divider ───────────────────────────────────────────────────
    tk.Frame(content, bg=DIVIDER, height=1).pack(fill="x", padx=P, pady=(22, 0))

    # ── Machine ID ────────────────────────────────────────────────
    mid_sec = tk.Frame(content, bg=BG)
    mid_sec.pack(fill="x", padx=P, pady=(20, 0))

    tk.Label(mid_sec, text="YOUR SYSTEM ID (MACHINE ID)",
             bg=BG, fg=TXT_D, font=("Segoe UI", 8, "bold"),
             anchor="w").pack(fill="x")
    tk.Label(mid_sec,
             text="Share this code with your software provider to receive an activation key.",
             bg=BG, fg=TXT_M, font=("Segoe UI", 9),
             anchor="w", wraplength=496, justify="left").pack(fill="x", pady=(3, 10))

    # Card
    mid_card = tk.Frame(mid_sec, bg=BG_CARD)
    mid_card.pack(fill="x")

    tk.Label(mid_card, text="  System ID / Machine ID",
             bg=BG_CARD, fg=TXT_D, font=("Segoe UI", 7, "bold"),
             anchor="w").pack(fill="x", pady=(10, 0))

    mid_entry = tk.Entry(
        mid_card,
        textvariable=tk.StringVar(value=machine_id),
        state="readonly", readonlybackground=BG_CARD,
        fg=MID_BLUE, font=("Consolas", 13, "bold"),
        bd=0, relief="flat", justify="center",
    )
    mid_entry.pack(fill="x", ipady=10, padx=12)

    tk.Frame(mid_card, bg=DIVIDER, height=1).pack(fill="x", pady=(8, 0))

    copy_row = tk.Frame(mid_card, bg=BG_CARD)
    copy_row.pack(fill="x", padx=12, pady=10)

    tk.Label(copy_row, text="Click to copy, then send to your provider",
             bg=BG_CARD, fg=TXT_D, font=("Segoe UI", 8)).pack(side="left")

    def _copy():
        root.clipboard_clear()
        root.clipboard_append(machine_id)
        copy_btn.config(text="  ✓ Copied!  ", bg=GREEN)
        root.after(2200, lambda: copy_btn.config(text="  Copy ID  ", bg=ACCENT))

    copy_btn = tk.Button(
        copy_row, text="  Copy ID  ", command=_copy,
        bg=ACCENT, fg="white",
        activebackground=ACCENT_H, activeforeground="white",
        relief="raised", bd=1, cursor="hand2",
        font=("Segoe UI", 9, "bold"), padx=10, pady=5,
    )
    copy_btn.pack(side="right")
    _hover(copy_btn, ACCENT, ACCENT_H)

    # ── Divider ───────────────────────────────────────────────────
    tk.Frame(content, bg=DIVIDER, height=1).pack(fill="x", padx=P, pady=(22, 0))

    # ── Activation key ────────────────────────────────────────────
    key_sec = tk.Frame(content, bg=BG)
    key_sec.pack(fill="x", padx=P, pady=(20, 0))

    tk.Label(key_sec, text="ACTIVATION KEY",
             bg=BG, fg=TXT_D, font=("Segoe UI", 8, "bold"),
             anchor="w").pack(fill="x")
    tk.Label(key_sec, text="Enter the key provided by your software supplier.",
             bg=BG, fg=TXT_M, font=("Segoe UI", 9),
             anchor="w").pack(fill="x", pady=(3, 10))

    key_card = tk.Frame(key_sec, bg=BG_CARD)
    key_card.pack(fill="x")

    tk.Label(key_card, text="  License Key",
             bg=BG_CARD, fg=TXT_D, font=("Segoe UI", 7, "bold"),
             anchor="w").pack(fill="x", pady=(10, 0))

    key_entry = tk.Entry(
        key_card, textvariable=key_var,
        bg=BG_CARD, fg=TXT_H,
        insertbackground=TXT_H,
        font=("Consolas", 12),
        bd=0, relief="flat", justify="center",
    )
    key_entry.pack(fill="x", ipady=10, padx=12, pady=(4, 0))

    ul = tk.Frame(key_card, bg=ACCENT, height=2)
    ul.pack(fill="x", pady=(6, 10))
    key_underline = ul   # now assign to the closure variable

    # ── Bindings ──────────────────────────────────────────────────
    root.bind("<Return>", lambda _e: _activate())
    root.protocol("WM_DELETE_WINDOW", _cancel)
    key_entry.focus_set()

    root.mainloop()
    return activated[0]
