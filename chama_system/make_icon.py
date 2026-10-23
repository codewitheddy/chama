"""Generate app.ico and default group_logo.png for desktop and web builds."""
from PIL import Image, ImageDraw, ImageFont
import os, struct, io, shutil
from pathlib import Path

# ── 1. Generate app.ico ───────────────────────────────────────────
sizes = [16, 32, 48, 256]
pngs = []

for size in sizes:
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    m = max(2, size // 16)
    draw.ellipse([m, m, size - m - 1, size - m - 1], fill='#1e3a5f')
    fs = max(int(size * 0.52), 10)
    try:
        font = ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf', fs)
        bbox = draw.textbbox((0, 0), 'F', font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text(
            ((size - tw) // 2 - bbox[0], (size - th) // 2 - bbox[1]),
            'F', fill='white', font=font
        )
    except Exception:
        pass
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    pngs.append(buf.getvalue())

# Build ICO file manually (PNG-in-ICO format, supported by Windows Vista+)
n = len(sizes)
header = struct.pack('<HHH', 0, 1, n)
offset = 6 + n * 16
directory = b''
for size, png in zip(sizes, pngs):
    w = 0 if size == 256 else size
    directory += struct.pack('<BBBBHHII', w, w, 0, 0, 1, 32, len(png), offset)
    offset += len(png)

with open('app.ico', 'wb') as f:
    f.write(header + directory)
    for png in pngs:
        f.write(png)

size_kb = os.path.getsize('app.ico') // 1024
print(f'app.ico created: {size_kb}KB, {n} sizes: {sizes}')

# ── 2. Generate default branding logo (media/branding/group_logo.png) ─
logo_size = 512
logo_img = Image.new('RGBA', (logo_size, logo_size), (0, 0, 0, 0))
logo_draw = ImageDraw.Draw(logo_img)

# Rounded rectangle background with navy #1e2a3a
pad = 24
radius = 80
logo_draw.rounded_rectangle(
    [pad, pad, logo_size - pad, logo_size - pad],
    radius=radius,
    fill='#1e2a3a'
)

# Inner decorative border / accent
inner_pad = pad + 16
logo_draw.rounded_rectangle(
    [inner_pad, inner_pad, logo_size - inner_pad, logo_size - inner_pad],
    radius=radius - 12,
    outline='#2563eb',
    width=6
)

# Text 'FW' or 'F'
try:
    font_large = ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf', 230)
    bbox = logo_draw.textbbox((0, 0), 'FW', font=font_large)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    logo_draw.text(
        ((logo_size - tw) // 2 - bbox[0], (logo_size - th) // 2 - bbox[1] - 20),
        'FW', fill='#ffffff', font=font_large
    )
    # Subtitle
    font_sub = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 38)
    sub_text = 'FINANCE WISE'
    s_bbox = logo_draw.textbbox((0, 0), sub_text, font=font_sub)
    s_w = s_bbox[2] - s_bbox[0]
    logo_draw.text(
        ((logo_size - s_w) // 2 - s_bbox[0], logo_size - pad - 65),
        sub_text, fill='#60a5fa', font=font_sub
    )
except Exception:
    pass

# Save to local media/branding/group_logo.png
local_branding = Path('media') / 'branding'
local_branding.mkdir(parents=True, exist_ok=True)
logo_path = local_branding / 'group_logo.png'
logo_img.save(logo_path, format='PNG')
print(f'group_logo.png created at: {logo_path.resolve()}')

# Save to AppData media/branding/group_logo.png if APPDATA exists
appdata = os.environ.get('APPDATA', '')
if appdata:
    appdata_branding = Path(appdata) / 'FinanceWiseTBM' / 'media' / 'branding'
    appdata_branding.mkdir(parents=True, exist_ok=True)
    appdata_logo = appdata_branding / 'group_logo.png'
    shutil.copy2(logo_path, appdata_logo)
    print(f'group_logo.png copied to AppData: {appdata_logo}')
