"""
Finance Wise TBM — Desktop Launcher
=====================================
Starts Django via Waitress on a free local port, then opens the app using
the best available renderer (tried in order):

  1. pywebview  — proper embedded chromium window (needs pythonnet + .NET)
  2. Edge/Chrome --app mode — native-looking window, no browser toolbar
  3. System browser + tkinter control panel — universal fallback

Usage:
    python desktop.py      # development / direct run
    FinanceWiseTBM.exe     # after PyInstaller build
"""

import os
import sys
import socket
import subprocess
import threading
import time
import logging
import webbrowser

# ── Ensure the bundled app directory is on sys.path when frozen ──
if getattr(sys, 'frozen', False):
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
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    APP_DIR  = BASE_DIR

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


# ── Django settings ───────────────────────────────────────────────
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'chama_system.settings')
os.environ['DEBUG']        = 'False'
os.environ['ALLOWED_HOSTS']= '127.0.0.1,localhost'
os.environ['DATABASE_URL'] = ''
os.environ['DB_HOST']      = ''
os.environ['DB_NAME']      = ''
os.environ['DB_USER']      = ''
os.environ['DB_PASSWORD']  = ''

if getattr(sys, 'frozen', False):
    import pathlib, shutil, platform
    # Persistent user data directory (isolated from application installation files across Windows, Linux, macOS)
    sys_name = platform.system().lower()
    home = pathlib.Path.home()
    if sys_name == 'windows':
        appdata = os.environ.get('APPDATA')
        data_dir = (pathlib.Path(appdata) if appdata else home / 'AppData' / 'Roaming') / 'FinanceWiseTBM'
    elif sys_name == 'darwin':
        data_dir = home / 'Library' / 'Application Support' / 'FinanceWiseTBM'
    else:
        xdg_data = os.environ.get('XDG_DATA_HOME')
        base = pathlib.Path(xdg_data) if xdg_data else home / '.local' / 'share'
        data_dir = base / 'FinanceWiseTBM'
    data_dir.mkdir(parents=True, exist_ok=True)

    target_db = data_dir / 'db.sqlite3'
    media_dir = data_dir / 'media'
    media_dir.mkdir(parents=True, exist_ok=True)

    # ── Update & Upgrade Data Preservation ─────────────────────────
    # If the user updated from an older installation where data might be in
    # APP_DIR or LOCALAPPDATA, migrate it once into the safe APPDATA location.
    if not target_db.exists():
        legacy_locations = [
            pathlib.Path(APP_DIR) / 'db.sqlite3',
            pathlib.Path(APP_DIR) / 'Data' / 'db.sqlite3',
            pathlib.Path(os.environ.get('LOCALAPPDATA', '')) / 'FinanceWiseTBM' / 'db.sqlite3' if os.environ.get('LOCALAPPDATA') else None,
            pathlib.Path(os.environ.get('PROGRAMDATA', '')) / 'FinanceWiseTBM' / 'db.sqlite3' if os.environ.get('PROGRAMDATA') else None,
        ]
        for candidate in legacy_locations:
            if candidate and candidate.is_file() and candidate.stat().st_size > 0:
                try:
                    shutil.copy2(candidate, target_db)
                    logging.info(f'Preserved user database from legacy location: {candidate} -> {target_db}')
                    break
                except Exception as e:
                    logging.warning(f'Could not migrate legacy database from {candidate}: {e}')

    os.environ['DESKTOP_DB_PATH'] = str(target_db)
    os.environ['DESKTOP_MEDIA_ROOT'] = str(media_dir)
else:
    import pathlib
    data_dir = pathlib.Path(BASE_DIR)
    os.environ.setdefault('DESKTOP_DB_PATH', str(data_dir / 'db.sqlite3'))
    os.environ.setdefault('DESKTOP_MEDIA_ROOT', str(data_dir / 'media'))

import django
django.setup()

# ── Database Migration & Compatibility Reconciler ─────────────────
# Ensures legacy databases automatically receive all latest migrations,
# welfare bank segregation, and system settings seamlessly on startup.
try:
    from utils.reconciler import reconcile_all
    reconcile_all(caller='desktop_startup')
except Exception as e:
    logging.warning(f'Reconciler warning (non-fatal): {e}')

# ── Health check endpoint for updater verification ────────────────
if '--health-check' in sys.argv:
    from django.core.management import call_command
    from django.db import connection
    try:
        call_command('check', verbosity=0)
        with connection.cursor() as cur:
            cur.execute('SELECT 1;')
        print('HEALTH_OK')
        sys.exit(0)
    except Exception as exc:
        print(f'HEALTH_CHECK_FAILED: {exc}', file=sys.stderr)
        sys.exit(1)


# ── Server helpers ────────────────────────────────────────────────

def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _start_server(port, error_holder):
    """Run Waitress. Any exception is stored in error_holder[0]."""
    try:
        from waitress import serve
        from chama_system.wsgi import application
        serve(application, host='127.0.0.1', port=port,
              threads=4, channel_timeout=60, _quiet=True)
    except Exception as exc:
        error_holder[0] = exc
        logging.exception('Waitress server crashed')


def _wait_for_server(port, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.15)
    return False


# ── pywebview check ───────────────────────────────────────────────

def _pywebview_available():
    """Return True if pywebview + its Windows dependencies are importable."""
    try:
        import webview  # noqa: F401
        if sys.platform == 'win32':
            import clr  # pythonnet — raises if .NET missing
        return True
    except Exception:
        return False


# ── Edge / Chrome --app mode ──────────────────────────────────────

def _find_chromium_exe():
    """Return path to Edge or Chrome if installed, else None."""
    candidates = [
        r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
        os.path.join(os.environ.get('LOCALAPPDATA', ''),
                     r'Microsoft\Edge\Application\msedge.exe'),
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
        os.path.join(os.environ.get('LOCALAPPDATA', ''),
                     r'Google\Chrome\Application\chrome.exe'),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def _launch_appmode(url: str, chromium_exe: str):
    """
    Launch Edge/Chrome in --app mode.
    This opens a window with no address bar, no tabs — looks like a native app.
    Uses a dedicated profile so it's isolated from the user's browser.
    """
    profile_dir = os.path.join(
        os.environ.get('APPDATA', APP_DIR), 'FinanceWiseTBM', 'BrowserProfile'
    )
    os.makedirs(profile_dir, exist_ok=True)
    subprocess.Popen([
        chromium_exe,
        f'--app={url}',
        f'--user-data-dir={profile_dir}',
        '--window-size=1280,820',
        '--disable-extensions',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-background-mode',
    ])


# ── tkinter control panel ─────────────────────────────────────────

def _run_control_window(url: str, title: str, mode: str):
    """
    Small always-on-top tkinter control window.
    Shown when pywebview is NOT available (app-mode or browser fallback).
    """
    import tkinter as tk
    from tkinter import messagebox

    BG     = '#1e2a3a'
    ACCENT = '#2563eb'
    TEXT_H = '#f1f5f9'
    TEXT_M = '#94a3b8'
    GREEN  = '#16a34a'
    AMBER  = '#d97706'

    mode_labels = {
        'appmode': ('App window (Edge/Chrome)', GREEN),
        'browser': ('System browser', AMBER),
    }
    mode_text, mode_color = mode_labels.get(mode, ('Running', GREEN))

    root = tk.Tk()
    root.title(title)
    root.configure(bg=BG)
    root.resizable(False, False)

    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    # Load icon if available
    ico = os.path.join(BASE_DIR, 'app.ico')
    if os.path.isfile(ico):
        try:
            root.iconbitmap(ico)
        except Exception:
            pass

    W, H = 360, 290
    root.update_idletasks()
    sx, sy = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f'{W}x{H}+{(sx - W) // 2}+{(sy - H) // 2}')

    # Top accent bar
    tk.Frame(root, bg=ACCENT, height=4).pack(fill='x')

    # Header
    hdr = tk.Frame(root, bg=BG)
    hdr.pack(fill='x', padx=24, pady=(18, 0))
    tk.Label(hdr, text='\U0001f3e6', bg=BG, fg=TEXT_H,
             font=('Segoe UI Emoji', 22)).pack(side='left', padx=(0, 10))
    col = tk.Frame(hdr, bg=BG)
    col.pack(side='left')
    tk.Label(col, text=title, bg=BG, fg=TEXT_H,
             font=('Segoe UI', 13, 'bold'), anchor='w').pack(fill='x')
    tk.Label(col, text='Finance Wise TBM', bg=BG, fg=TEXT_M,
             font=('Segoe UI', 9), anchor='w').pack(fill='x')

    tk.Frame(root, bg='#2c3e52', height=1).pack(fill='x', padx=24, pady=(14, 0))

    # Status row — server running + mode badge
    status_row = tk.Frame(root, bg=BG)
    status_row.pack(fill='x', padx=24, pady=8)
    tk.Label(status_row, text='\u25cf', bg=BG, fg=GREEN,
             font=('Segoe UI', 10)).pack(side='left')
    tk.Label(status_row, text='  Server running  ', bg=BG, fg=TEXT_M,
             font=('Segoe UI', 9)).pack(side='left')
    tk.Label(status_row, text=mode_text, bg=BG, fg=mode_color,
             font=('Segoe UI', 8, 'bold')).pack(side='left')

    # Clickable URL
    url_lbl = tk.Label(root, text=url, bg=BG, fg=ACCENT,
                       font=('Consolas', 9), cursor='hand2')
    url_lbl.pack(padx=24, anchor='w')
    url_lbl.bind('<Button-1>', lambda _: webbrowser.open(url))

    tk.Frame(root, bg='#2c3e52', height=1).pack(fill='x', padx=24, pady=(14, 0))

    # Buttons
    btn_frame = tk.Frame(root, bg=BG)
    btn_frame.pack(fill='x', padx=24, pady=(12, 0))
    btn_frame.columnconfigure(0, weight=1)
    btn_frame.columnconfigure(1, weight=1)

    def _open():
        chromium = _find_chromium_exe()
        if chromium:
            _launch_appmode(url, chromium)
        else:
            webbrowser.open(url)
        open_btn.config(state='disabled')
        root.after(3000, lambda: open_btn.config(state='normal'))

    def _quit():
        if messagebox.askyesno('Exit', 'Stop Finance Wise TBM and close?', parent=root):
            root.destroy()

    open_label = 'Open App Window' if mode == 'appmode' else 'Open in Browser'
    open_btn = tk.Button(
        btn_frame, text=open_label,
        command=_open,
        bg=ACCENT, fg='white',
        activebackground='#1d4ed8', activeforeground='white',
        relief='raised', bd=1, cursor='hand2',
        font=('Segoe UI', 10, 'bold'), pady=9,
    )
    open_btn.grid(row=0, column=0, sticky='ew', padx=(0, 6))

    quit_btn = tk.Button(
        btn_frame, text='Exit',
        command=_quit,
        bg='#334155', fg=TEXT_H,
        activebackground='#475569', activeforeground=TEXT_H,
        relief='raised', bd=1, cursor='hand2',
        font=('Segoe UI', 10), pady=9,
    )
    quit_btn.grid(row=0, column=1, sticky='ew')

    tk.Label(root, text='Close this window to stop the server.',
             bg=BG, fg='#475569', font=('Segoe UI', 7)).pack(pady=(10, 14))

    root.protocol('WM_DELETE_WINDOW', _quit)
    root.mainloop()


def main():
    # ── Enforce node-locked license activation ────────────────────────
    from licensing import is_activated, get_machine_id
    from activation_ui import show_activation_window

    if not is_activated():
        mid = get_machine_id()
        activated = show_activation_window(mid)
        if not activated:
            sys.exit(0)

    port = _find_free_port()
    url  = f'http://127.0.0.1:{port}'

    # Start Waitress in background thread — capture any startup exception
    error_holder = [None]
    t = threading.Thread(target=_start_server, args=(port, error_holder), daemon=True)
    t.start()

    # Wait until server is ready (up to 30s)
    if not _wait_for_server(port):
        import tkinter as tk
        from tkinter import messagebox, scrolledtext

        # Collect the error message
        err = error_holder[0]
        if err:
            detail = f'{type(err).__name__}: {err}'
        else:
            detail = 'The server did not respond within 30 seconds.'

        # Write to a log file next to the exe for diagnostics
        try:
            import pathlib, traceback
            log_dir = pathlib.Path(os.environ.get('APPDATA', APP_DIR)) / 'FinanceWiseTBM'
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / 'startup_error.log'
            with open(log_path, 'w') as lf:
                lf.write(f'Server failed to start.\n\n{detail}\n')
                if err:
                    traceback.print_exc(file=lf)
        except Exception:
            pass

        root = tk.Tk()
        root.title('Finance Wise TBM — Startup Error')
        root.configure(bg='#1e2a3a')
        root.resizable(True, True)
        W, H = 560, 320
        root.update_idletasks()
        sx, sy = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f'{W}x{H}+{(sx-W)//2}+{(sy-H)//2}')

        tk.Frame(root, bg='#e11d48', height=4).pack(fill='x')
        tk.Label(root, text='Server failed to start', bg='#1e2a3a', fg='#f1f5f9',
                 font=('Segoe UI', 12, 'bold')).pack(pady=(16, 4))
        tk.Label(root, text='Error details:', bg='#1e2a3a', fg='#94a3b8',
                 font=('Segoe UI', 9)).pack(anchor='w', padx=16)

        txt = scrolledtext.ScrolledText(root, bg='#0f172a', fg='#f1f5f9',
                                        font=('Consolas', 9), height=8,
                                        relief='flat', bd=0)
        txt.pack(fill='both', expand=True, padx=16, pady=(4, 8))
        txt.insert('end', detail)
        txt.config(state='disabled')

        try:
            log_path_str = str(log_path)
        except Exception:
            log_path_str = ''

        def _copy():
            root.clipboard_clear()
            root.clipboard_append(detail)

        bf = tk.Frame(root, bg='#1e2a3a')
        bf.pack(fill='x', padx=16, pady=(0, 12))
        tk.Button(bf, text='Copy Error', command=_copy,
                  bg='#2563eb', fg='white', relief='flat', padx=12, pady=6,
                  font=('Segoe UI', 9)).pack(side='left', padx=(0, 8))
        tk.Button(bf, text='Close', command=root.destroy,
                  bg='#334155', fg='#f1f5f9', relief='flat', padx=12, pady=6,
                  font=('Segoe UI', 9)).pack(side='left')
        if log_path_str:
            tk.Label(bf, text=f'Log: {log_path_str}', bg='#1e2a3a', fg='#475569',
                     font=('Segoe UI', 7)).pack(side='right')

        root.mainloop()
        sys.exit(1)

    # Resolve group name for the window title
    try:
        from loans.models import SystemSetting
        title = SystemSetting.get('group_name', 'Finance Wise TBM')
    except Exception:
        title = 'Finance Wise TBM'

    # ── Non-blocking background check for updates on startup ───────
    try:
        from updater.services import UpdateService
        UpdateService().check_for_updates_async()
    except Exception as exc:
        logging.info(f"Background update check notice: {exc}")

    # ── Strategy 1: pywebview on the main thread ──────────────────
    if _pywebview_available():
        try:
            import webview
            window = webview.create_window(
                title=title,
                url=url,
                width=1280,
                height=820,
                min_size=(900, 600),
                resizable=True,
                text_select=True,
                confirm_close=True,
            )
            # start() blocks until the window is closed — runs on main thread
            webview.start(debug=False)
            return  # window closed = user is done
        except Exception as exc:
            logging.warning(f'pywebview failed ({exc}), falling back to app-mode')

    # ── Strategy 2: Edge / Chrome --app mode ─────────────────────
    chromium = _find_chromium_exe()
    if chromium:
        try:
            _launch_appmode(url, chromium)
            _run_control_window(url, title, mode='appmode')
            return
        except Exception as exc:
            logging.warning(f'App-mode failed ({exc}), falling back to browser')

    # ── Strategy 3: System browser ────────────────────────────────
    webbrowser.open(url)
    _run_control_window(url, title, mode='browser')


if __name__ == '__main__':
    main()
