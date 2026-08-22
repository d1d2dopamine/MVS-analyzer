# Assets

Visual assets that ship with the repository. Everything here is generated from
the master logo renders; nothing in this folder is required for the application
to run.

## What is here

```text
docs/assets/logo.png          512 x 512, header image at the top of README.md (both language halves)
```

Two more branding files live outside this folder because the build needs them
at those exact paths:

```text
app.ico                       multi-size window / taskbar / Explorer icon, 16 to 256 px, transparent
Assets/inapp_logo.png         908 x 412 wordmark shown on the Home page of the application
```

Both are declared as `EmbeddedResource` in `MvsAnalyzer.csproj`, so the
published single-file executable carries its own branding with no loose images
next to it. `Branding.cs` reads them by resource-name suffix and fails soft: if
an asset is missing or damaged, the window falls back to the icon extracted from
the executable and the Home page simply starts with its first card.

## Regenerating the icon

The master render has a white background; the icon needs a transparent one. The
background is removed by a flood fill that starts at the image border, so white
areas *inside* the mark are preserved. Any Pillow install can redo it:

```python
from PIL import Image
import numpy as np
from collections import deque

im = Image.open("app_logo.jpeg").convert("RGB")
a = np.asarray(im).astype(np.int16)
h, w, _ = a.shape
mn = a.min(axis=2)
loose = (mn > 200) & (a.max(axis=2) - mn < 34)

visited = np.zeros((h, w), bool)
dq = deque()
for x in range(w):
    for y in (0, h - 1):
        if loose[y, x] and not visited[y, x]:
            visited[y, x] = True; dq.append((y, x))
for y in range(h):
    for x in (0, w - 1):
        if loose[y, x] and not visited[y, x]:
            visited[y, x] = True; dq.append((y, x))
while dq:
    y, x = dq.popleft()
    for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
        if 0 <= ny < h and 0 <= nx < w and loose[ny, nx] and not visited[ny, nx]:
            visited[ny, nx] = True; dq.append((ny, nx))

alpha = np.full((h, w), 255, np.int16)
alpha[visited] = np.clip((245 - mn) * 255 // 45, 0, 255)[visited]   # soft, anti-aliased edge
logo = Image.fromarray(np.dstack([a.astype(np.uint8), alpha.astype(np.uint8)]), "RGBA")
logo = logo.crop(logo.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox())

side = max(logo.size)
pad = int(side * 0.04)
canvas = Image.new("RGBA", (side + 2 * pad, side + 2 * pad), (0, 0, 0, 0))
canvas.paste(logo, ((canvas.width - logo.width) // 2, (canvas.height - logo.height) // 2))

sizes = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
frames = [canvas.resize((s, s), Image.LANCZOS) for s in sizes]
frames[-1].save("app.ico", sizes=[(s, s) for s in sizes], append_images=frames[:-1])
```

Keep all ten sizes: Windows picks 16 px for the title bar, 32 px for the
taskbar, and 256 px for large Explorer views and high-DPI displays.

## Social preview

GitHub's link card wants a 1280 x 640 PNG uploaded in **Settings -> General ->
Social preview**. It is not part of the repository.

## Screenshots

Same folder, same naming pattern:

```text
docs/assets/screenshot-results.png
docs/assets/screenshot-calibration.png
docs/assets/screenshot-audit.png
```

Guidelines that keep the README fast and honest:

- PNG, no larger than ~300 KB each - run them through a compressor;
- capture at 100 % display scaling, light **and** dark theme if you show both;
- use the bundled `examples/` datasets, never real measurement data;
- always set meaningful `alt` text;
- keep them in `docs/`, not in the repository root.

## What not to put here

- Build outputs, run folders, or anything from `%LocalAppData%\MVS_Analyzer\`.
- Real datasets or anything with identifiable device serials or subject ids.
- Large binaries - GitHub renders a README slowly when it has to fetch
  megabytes of images.
