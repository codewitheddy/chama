"""
Finance Wise TBM — Emergency Password Reset Tool
=================================================
Double-click this file (or run: python reset_password.py) from the
chama_system folder to reset an admin password without logging in.

Works fully offline — no email or internet required.
"""
import os
import sys
import pathlib

# ── Locate the app directory ──────────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    # Running inside the PyInstaller bundle
    BASE_DIR = sys._MEIPASS
    APP_DIR  = os.path.dirname(sys.executable)
    env_file = os.path.join(BASE_DIR, 'desktop.env')
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, _, v = line.partition('=')
                    os.environ.setdefault(k.strip(), v.strip())
    data_dir = pathlib.Path(os.environ.get('APPDATA', APP_DIR)) / 'FinanceWiseTBM'
    os.environ['DESKTOP_DB_PATH'] = str(data_dir / 'db.sqlite3')
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    APP_DIR  = BASE_DIR

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'chama_system.settings')
os.environ['DEBUG']        = 'False'
os.environ['ALLOWED_HOSTS'] = '127.0.0.1,localhost'

import django
django.setup()

# ── GUI ───────────────────────────────────────────────────────────────────────
import tkinter as tk
from tkinter import ttk, messagebox
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

BG     = '#1e2a3a'
ACCENT = '#2563eb'
TEXT_H = '#f1f5f9'
TEXT_M = '#94a3b8'
WHITE  = '#ffffff'
RED    = '#e11d48'


def main():
    root = tk.Tk()
    root.title('Finance Wise TBM — Password Reset')
    root.configure(bg=BG)
    root.resizable(False, False)

    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    ico = os.path.join(BASE_DIR, 'app.ico')
    if os.path.isfile(ico):
        try:
            root.iconbitmap(ico)
        except Exception:
            pass

    W, H = 420, 420
    root.update_idletasks()
    sx, sy = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f'{W}x{H}+{(sx - W) // 2}+{(sy - H) // 2}')

    # Title bar accent
    tk.Frame(root, bg=ACCENT, height=4).pack(fill='x')

    # Header
    hdr = tk.Frame(root, bg=BG)
    hdr.pack(fill='x', padx=24, pady=(18, 0))
    tk.Label(hdr, text='\U0001f512', bg=BG, fg=TEXT_H,
             font=('Segoe UI Emoji', 22)).pack(side='left', padx=(0, 10))
    col = tk.Frame(hdr, bg=BG)
    col.pack(side='left')
    tk.Label(col, text='Password Reset', bg=BG, fg=TEXT_H,
             font=('Segoe UI', 13, 'bold'), anchor='w').pack(fill='x')
    tk.Label(col, text='Finance Wise TBM', bg=BG, fg=TEXT_M,
             font=('Segoe UI', 9), anchor='w').pack(fill='x')

    tk.Frame(root, bg='#2c3e52', height=1).pack(fill='x', padx=24, pady=(14, 0))

    # Form frame
    frm = tk.Frame(root, bg=BG)
    frm.pack(fill='x', padx=24, pady=16)

    # User selector
    users = User.objects.filter(is_active=True).order_by('username')
    if not users.exists():
        messagebox.showerror(
            'No Users Found',
            'No user accounts found in the database.\n'
            'The database may be empty or in a different location.'
        )
        root.destroy()
        return

    user_names = [u.username for u in users]

    tk.Label(frm, text='Select User', bg=BG, fg=TEXT_M,
             font=('Segoe UI', 9), anchor='w').pack(fill='x', pady=(0, 4))
    user_var = tk.StringVar(value=user_names[0])
    combo = ttk.Combobox(frm, textvariable=user_var, values=user_names,
                         state='readonly', font=('Segoe UI', 10))
    combo.pack(fill='x', pady=(0, 12))

    tk.Label(frm, text='New Password', bg=BG, fg=TEXT_M,
             font=('Segoe UI', 9), anchor='w').pack(fill='x', pady=(0, 4))
    pw_var = tk.StringVar()
    pw_entry = tk.Entry(frm, textvariable=pw_var, show='●',
                        font=('Segoe UI', 11), relief='flat',
                        bg='#263347', fg=WHITE, insertbackground=WHITE,
                        highlightthickness=1, highlightbackground='#2c3e52',
                        highlightcolor=ACCENT)
    pw_entry.pack(fill='x', ipady=6, pady=(0, 12))

    tk.Label(frm, text='Confirm New Password', bg=BG, fg=TEXT_M,
             font=('Segoe UI', 9), anchor='w').pack(fill='x', pady=(0, 4))
    pw2_var = tk.StringVar()
    pw2_entry = tk.Entry(frm, textvariable=pw2_var, show='●',
                         font=('Segoe UI', 11), relief='flat',
                         bg='#263347', fg=WHITE, insertbackground=WHITE,
                         highlightthickness=1, highlightbackground='#2c3e52',
                         highlightcolor=ACCENT)
    pw2_entry.pack(fill='x', ipady=6, pady=(0, 4))

    # Show/hide password toggle
    show_var = tk.BooleanVar(value=False)
    def toggle_show():
        ch = '' if show_var.get() else '●'
        pw_entry.config(show=ch)
        pw2_entry.config(show=ch)
    tk.Checkbutton(frm, text='Show password', variable=show_var,
                   command=toggle_show, bg=BG, fg=TEXT_M,
                   activebackground=BG, activeforeground=TEXT_M,
                   selectcolor='#263347', font=('Segoe UI', 8)).pack(anchor='w')

    # Status label
    status_var = tk.StringVar()
    status_lbl = tk.Label(frm, textvariable=status_var, bg=BG,
                          font=('Segoe UI', 8), wraplength=360, anchor='w')
    status_lbl.pack(fill='x', pady=(8, 0))

    # Buttons
    btn_frame = tk.Frame(root, bg=BG)
    btn_frame.pack(fill='x', padx=24, pady=(4, 18))
    btn_frame.columnconfigure(0, weight=1)
    btn_frame.columnconfigure(1, weight=1)

    def do_reset():
        username = user_var.get().strip()
        pw       = pw_var.get()
        pw2      = pw2_var.get()

        if not pw:
            status_var.set('Please enter a new password.')
            status_lbl.config(fg=RED)
            return
        if len(pw) < 6:
            status_var.set('Password must be at least 6 characters.')
            status_lbl.config(fg=RED)
            return
        if pw != pw2:
            status_var.set('Passwords do not match.')
            status_lbl.config(fg=RED)
            return

        try:
            user = User.objects.get(username=username)
            user.set_password(pw)
            user.save()
            status_var.set(f'✓ Password for "{username}" has been reset successfully.')
            status_lbl.config(fg='#4ade80')
            pw_var.set('')
            pw2_var.set('')
            messagebox.showinfo(
                'Password Reset',
                f'Password for "{username}" has been reset.\n\nYou can now log in with the new password.',
            )
        except User.DoesNotExist:
            status_var.set(f'User "{username}" not found.')
            status_lbl.config(fg=RED)
        except Exception as e:
            status_var.set(f'Error: {e}')
            status_lbl.config(fg=RED)

    reset_btn = tk.Button(
        btn_frame, text='Reset Password',
        command=do_reset,
        bg=ACCENT, fg=WHITE,
        activebackground='#1d4ed8', activeforeground=WHITE,
        relief='raised', bd=1, cursor='hand2',
        font=('Segoe UI', 10, 'bold'), pady=9,
    )
    reset_btn.grid(row=0, column=0, sticky='ew', padx=(0, 6))

    close_btn = tk.Button(
        btn_frame, text='Close',
        command=root.destroy,
        bg='#334155', fg=TEXT_H,
        activebackground='#475569', activeforeground=TEXT_H,
        relief='raised', bd=1, cursor='hand2',
        font=('Segoe UI', 10), pady=9,
    )
    close_btn.grid(row=0, column=1, sticky='ew')

    # Bind Enter key
    root.bind('<Return>', lambda e: do_reset())
    pw_entry.focus_set()
    root.mainloop()


if __name__ == '__main__':
    main()
