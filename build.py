#!/usr/bin/env python3
"""Build the Bellwether web bundle.

`index.html` at the repo root is the single source of truth: a clean, fully
offline file you can double-click from disk. This script copies it into
`docs/` with the PWA plumbing injected (manifest link, theme tags, service
worker registration) and generates the icons and manifest alongside it.

`docs/` is what both hosts serve:
  Cloudflare Pages  wrangler pages deploy docs --project-name bellwether
  GitHub Pages      repo settings -> Pages -> main branch, /docs folder

Bump VERSION with every change you publish. It drives the service worker
cache name, so an old cached copy is replaced rather than lingering.
"""

import os
import re
import struct
import zlib

VERSION = "2.2"
HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(HERE, "docs")

# Spectrum, matching the app's --g1..--g4 tokens. The icon is the gradient
# tile with the mark knocked out of it, exactly as the header shows it.
GRAD = [(0.00, (139, 92, 246)),    # violet
        (0.38, (236, 72, 153)),    # pink
        (0.68, (249, 115, 98)),    # coral
        (1.00, (251, 191, 36))]    # gold
GLYPH = (18, 10, 28)               # --accent-ink


def grad_at(t):
    """Colour at position t along the gradient, linearly interpolated."""
    t = max(0.0, min(1.0, t))
    for i in range(len(GRAD) - 1):
        a, ca = GRAD[i]
        b, cb = GRAD[i + 1]
        if t <= b:
            f = 0.0 if b == a else (t - a) / (b - a)
            return tuple(int(ca[k] + (cb[k] - ca[k]) * f) for k in range(3))
    return GRAD[-1][1]


# ---------------------------------------------------------------- png writer

def write_png(path, width, height, rgb_rows):
    """Write an 8-bit RGB PNG. rgb_rows is a list of bytearrays, one per row."""
    raw = b"".join(b"\x00" + bytes(row) for row in rgb_rows)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def dist_to_segment(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = x1 + t * dx, y1 + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def make_icon(path, size):
    """Draw the Bellwether mark: a rising line, a marked turn, a corner arrow."""
    ss = 2                      # supersample factor
    n = size * ss
    unit = n / 32.0             # the source glyph is a 32x32 viewBox

    # glyph geometry, in viewBox units
    segments = [
        (6, 22.5, 12, 15), (12, 15, 17, 19), (17, 19, 26, 8.5),   # the line
        (21.5, 8.5, 26, 8.5), (26, 8.5, 26, 13),                  # the arrow
    ]
    # Shrink about the centre so the mark survives a maskable circular crop,
    # which keeps only the middle 80% of the icon.
    k = 0.82
    sc = lambda v: (16 + (v - 16) * k) * unit
    segments = [(sc(a), sc(b), sc(c), sc(d)) for a, b, c, d in segments]
    stroke = 2.6 * k * unit / 2.0

    big = []
    for y in range(n):
        row = bytearray()
        for x in range(n):
            px, py = x + 0.5, y + 0.5

            # background: the gradient swept at 115 degrees, as in the app
            col = grad_at((px * 0.78 + py * 0.36) / (n * 1.06))

            for (x1, y1, x2, y2) in segments:
                if dist_to_segment(px, py, x1, y1, x2, y2) <= stroke:
                    col = GLYPH
                    break

            row += bytes(col)
        big.append(row)

    # downsample the supersampled buffer
    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            r = g = b = 0
            for dy in range(ss):
                src = big[y * ss + dy]
                for dx in range(ss):
                    i = (x * ss + dx) * 3
                    r += src[i]; g += src[i + 1]; b += src[i + 2]
            k = ss * ss
            row += bytes((r // k, g // k, b // k))
        rows.append(row)

    write_png(path, size, size, rows)
    print("  icon", os.path.basename(path), size)


# ---------------------------------------------------------------- web bundle

PWA_HEAD = """<link rel="manifest" href="./manifest.webmanifest" />
<link rel="apple-touch-icon" href="./apple-touch-icon.png" />
<meta name="apple-mobile-web-app-capable" content="yes" />
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
<meta name="apple-mobile-web-app-title" content="Bellwether" />
<meta name="mobile-web-app-capable" content="yes" />
"""

SW_REG = """
/* Service worker: http(s) only, so the offline file:// copy stays plain. */
if ("serviceWorker" in navigator && location.protocol.startsWith("http")) {
  window.addEventListener("load", function(){
    navigator.serviceWorker.register("./sw.js").catch(function(){});
  });
}
"""

MANIFEST = """{
  "name": "Bellwether",
  "short_name": "Bellwether",
  "description": "A private watchlist, portfolio tracker, screener and trade journal.",
  "start_url": "./",
  "scope": "./",
  "display": "standalone",
  "orientation": "portrait-primary",
  "background_color": "#0c0812",
  "theme_color": "#0c0812",
  "icons": [
    { "src": "./icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable" },
    { "src": "./icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable" }
  ]
}
"""

SW = """const CACHE = "bellwether-v%s";
const ASSETS = ["./", "./index.html", "./manifest.webmanifest", "./icon-192.png", "./icon-512.png", "./apple-touch-icon.png"];
self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  const url = new URL(e.request.url);
  /* Never cache the price providers: stale quotes are worse than none. */
  if (url.origin !== location.origin) return;

  /* The page and the manifest go to the network first. Cache-first here means
     the first load after a deploy serves the PREVIOUS version and only the
     second load shows the new one, which reads as "my change did not ship".
     Offline still works: the fetch fails and we fall back to the cache. */
  const isDoc = e.request.mode === "navigate"
             || url.pathname.endsWith("/")
             || url.pathname.endsWith(".html")
             || url.pathname.endsWith(".webmanifest");

  if (isDoc) {
    e.respondWith(
      fetch(e.request).then(res => {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, copy));
        return res;
      }).catch(() => caches.match(e.request).then(hit => hit || caches.match("./index.html")))
    );
    return;
  }

  /* Static assets are content-addressed by the cache name, so cache-first. */
  e.respondWith(
    caches.match(e.request).then(hit => hit || fetch(e.request).then(res => {
      const copy = res.clone();
      caches.open(CACHE).then(c => c.put(e.request, copy));
      return res;
    }))
  );
});
"""


def build():
    os.makedirs(DOCS, exist_ok=True)

    with open(os.path.join(HERE, "index.html"), encoding="utf-8") as f:
        html = f.read()

    if "</head>" not in html or "</script>" not in html:
        raise SystemExit("index.html does not look like the app; refusing to build.")

    web = html.replace("</head>", PWA_HEAD + "</head>", 1)
    # Stamp the build version beside the theme-color tag. Anchored by a regex
    # rather than a literal colour, so a palette change cannot silently turn
    # this into a no-op, and it raises rather than shipping an unstamped page.
    web, n = re.subn(r'(<meta name="theme-color"[^>]*/>)',
                     r'\1\n<meta name="bw-version" content="%s" />' % VERSION, web, count=1)
    if n != 1:
        raise SystemExit("could not find the theme-color meta tag to stamp the version onto")
    # append the registration to the app's own closing script tag
    idx = web.rindex("</script>")
    web = web[:idx] + SW_REG + web[idx:]

    out = os.path.join(DOCS, "index.html")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(web)
    print("  docs/index.html  %.0f KB" % (len(web.encode()) / 1024))

    with open(os.path.join(DOCS, "manifest.webmanifest"), "w", encoding="utf-8", newline="\n") as f:
        f.write(MANIFEST)
    with open(os.path.join(DOCS, "sw.js"), "w", encoding="utf-8", newline="\n") as f:
        f.write(SW % VERSION)
    with open(os.path.join(DOCS, ".nojekyll"), "w") as f:
        f.write("")

    for name, size in (("icon-192.png", 192), ("icon-512.png", 512), ("apple-touch-icon.png", 180)):
        p = os.path.join(DOCS, name)
        if not os.path.exists(p) or os.environ.get("BW_ICONS"):
            make_icon(p, size)
        else:
            print("  icon", name, "(kept, set BW_ICONS=1 to redraw)")

    print("Built Bellwether %s into docs/" % VERSION)


if __name__ == "__main__":
    build()
