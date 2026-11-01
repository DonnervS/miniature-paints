#!/usr/bin/env python3
"""Build paints.json from the per-brand markdown tables in paints/markdown/.

Each paints/markdown/<Brand>.md file holds:
  * an H1 title  -> brand displayName
  * a "Brand Details" key/value table -> company / address / contact info
  * a paints table (Name, [Code], Set, R, G, B, Hex) -> the paint list

The generated paints.json is fully derived from these files, so the markdown
is the single source of truth. Run this whenever a brand .md file changes.
"""
import os, re, json, glob
from collections import OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAINTS_DIR = os.path.join(ROOT, "paints", "markdown")
OUT_PATH = os.path.join(ROOT, "paints", "paints.json")
JSON_DIR = os.path.join(ROOT, "paints", "json")
MEASUREMENTS_PATH = os.path.join(ROOT, "measurements", "measurements.csv")

# Dataset schema version, and the JSON Schema files each output document links to via
# "$schema" (relative to the document's own location). See schema/ at the repo root.
SCHEMA_VERSION = "miniature-paints/v5"
AGG_SCHEMA_REF = "../schema/paints.schema.json"        # for paints/paints.json
BRAND_SCHEMA_REF = "../../schema/brand.schema.json"    # for paints/json/<stem>.json

HEX_RE = re.compile(r'#([0-9A-Fa-f]{6})')
POT_RE = re.compile(r'([\d]+(?:\.[\d]+)?)\s*([a-zA-Z]+)')


def parse_pot_sizes(raw):
    """'37ml, 60ml, 250ml' -> [ {...}, {...}, {...} ]; '17ml' -> [ {...} ]; falsy -> None.

    A paint may be sold in several sizes; the Pot Size cell lists them comma-separated.
    Each size becomes one {'raw','value','unit'} object; unparseable parts keep raw only.
    """
    if not raw:
        return None
    out = []
    for part in (p.strip() for p in raw.split(',')):
        if not part:
            continue
        m = POT_RE.search(part)
        if not m:
            out.append({"raw": part, "value": None, "unit": None})
            continue
        value = float(m.group(1))
        if value.is_integer():
            value = int(value)
        out.append({"raw": part, "value": value, "unit": m.group(2).lower()})
    return out or None

# Brand Details table field -> location in the brand object.
# ("address", k) nests under address; (None, k) sits at brand top level.
DETAIL_MAP = {
    "company":  (None, "company"),
    "address":  ("address", "street"),
    "city":     ("address", "city"),
    "postcode": ("address", "postcode"),
    "country":  ("address", "country"),
    "email":    (None, "contactEmail"),
    "contact form": (None, "contactForm"),
    "website":  (None, "website"),
    "phone":    (None, "phone"),
    "updated catalogue requested": (None, "updatedCatalogueRequested"),
}


def fix(s):
    """Repair latin1-mis-decoded utf-8 mojibake if present."""
    try:
        return s.encode('latin1').decode('utf-8')
    except Exception:
        return s


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def cells(line):
    return [c.strip() for c in line.split('|')[1:-1]]


def parse_details(lines):
    """Return dict of lowercased field -> value from the Brand Details table."""
    out = {}
    start = next((i for i, l in enumerate(lines)
                  if l.strip().lower() == '## brand details'), None)
    if start is None:
        return out
    # find the '| Field | Value |' header after the heading
    hdr = next((i for i in range(start, min(start + 6, len(lines)))
                if lines[i].startswith('|') and 'Field' in lines[i] and 'Value' in lines[i]), None)
    if hdr is None:
        return out
    for l in lines[hdr + 2:]:
        if not l.startswith('|'):
            break
        c = cells(l)
        if len(c) >= 2 and c[0]:
            out[c[0].strip().lower()] = fix(c[1].strip())
    return out


def parse_paints(lines, brand_slug):
    header_idx = next((i for i, l in enumerate(lines)
                       if l.startswith('|') and 'Name' in l and 'Hex' in l), None)
    if header_idx is None:
        return []
    header = cells(lines[header_idx])

    paints, used_ids = [], set()
    for l in lines[header_idx + 2:]:
        if not l.startswith('|'):
            break
        c = cells(l)
        if not any(c):
            continue
        row = dict(zip(header, c))

        name = fix(row.get('Name', '').strip())
        code = fix(row.get('Code', '').strip()) if 'Code' in header else ''
        code = code or None
        ean = [e.strip() for e in re.split(r'[,;\s]+', fix(row.get('EAN', ''))) if e.strip()] or None
        setv = fix(row.get('Set', '').strip()) or None
        pots = parse_pot_sizes(fix(row.get('Pot Size', '').strip()) or None)
        desc = fix(row.get('Description', '').strip()) or None

        def to_int(v):
            v = (v or '').strip()
            return int(v) if v.isdigit() else None
        R, G, B = to_int(row.get('R')), to_int(row.get('G')), to_int(row.get('B'))

        # A normal paint's Hex cell repeats one colour (alt text, placehold URL,
        # backtick code); a colour-shift paint lists several distinct stops. Dedupe
        # preserving order: one unique colour -> hex/rgb; several -> shiftColors.
        seen, hexes = set(), []
        for h in HEX_RE.findall(row.get('Hex', '')):
            h = '#' + h.upper()
            if h not in seen:
                seen.add(h)
                hexes.append(h)
        if len(hexes) >= 2:
            hexv, shift_colors = None, hexes
        else:
            hexv, shift_colors = (hexes[0] if hexes else None), None

        # A colourless product (clear varnish, medium, thinner, etc.) is flagged
        # by the literal word "colourless" in the Hex cell instead of a colour.
        # It has no hex/rgb and is not a colour-shift paint.
        colourless = 'colourless' in row.get('Hex', '').lower()
        if colourless:
            hexv, shift_colors = None, None
            R = G = B = None

        base = f"{brand_slug}-{slug(code) if code else slug(name)}"
        pid, n = base, 2
        while pid in used_ids:
            pid = f"{base}-{n}"
            n += 1
        used_ids.add(pid)

        paints.append({
            "id": pid,
            "name": name,
            "code": code,
            "ean": ean,
            "set": setv,
            "hex": hexv,
            "rgb": {"r": R, "g": G, "b": B} if None not in (R, G, B) else None,
            "shiftColors": shift_colors,
            "colourless": colourless,
            "potSizes": pots,
            "description": desc,
            "measurements": None,
            "measuredHex": None,
        })
    return paints


# --- Measured colours -------------------------------------------------------
# measurements/measurements.csv holds instrument readings (e.g. Nix Spectro,
# Datacolor ColorReader) of dried paint swatches. They are keyed by paint id and
# attached to the paint as "measurements"; "measuredHex" is the sRGB colour of
# their average, converted from CIELAB with chromatic adaptation where needed.

WHITE = {"D50": (0.96422, 1.0, 0.82521), "D65": (0.95047, 1.0, 1.08883)}
BRADFORD = ((0.8951, 0.2664, -0.1614), (-0.7502, 1.7135, 0.0367), (0.0389, -0.0685, 1.0296))
XYZ_TO_SRGB = ((3.2404542, -1.5371385, -0.4985314), (-0.9692660, 1.8760108, 0.0415560),
               (0.0556434, -0.2040259, 1.0572252))


def _mul(m, v):
    return tuple(sum(m[i][j] * v[j] for j in range(3)) for i in range(3))


def _inv3(m):
    a, b, c = m[0]; d, e, f = m[1]; g, h, i = m[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    return ((( e * i - f * h) / det, -(b * i - c * h) / det, (b * f - c * e) / det),
            (-(d * i - f * g) / det, (a * i - c * g) / det, -(a * f - c * d) / det),
            (( d * h - e * g) / det, -(a * h - b * g) / det, (a * e - b * d) / det))


def lab_to_hex(L, a, b, illuminant="D50"):
    """CIELAB (given white point) -> sRGB hex (D65), Bradford-adapted, clipped."""
    wx, wy, wz = WHITE[illuminant]
    fy = (L + 16) / 116
    fx, fz = fy + a / 500, fy - b / 200
    finv = lambda t: t ** 3 if t ** 3 > 216 / 24389 else (116 * t - 16) / (24389 / 27)
    xyz = (wx * finv(fx), wy * (fy ** 3 if L > 8 else L / (24389 / 27)), wz * finv(fz))
    if illuminant != "D65":
        src, dst = _mul(BRADFORD, WHITE[illuminant]), _mul(BRADFORD, WHITE["D65"])
        cone = _mul(BRADFORD, xyz)
        xyz = _mul(_inv3(BRADFORD), tuple(cone[k] * dst[k] / src[k] for k in range(3)))
    out = []
    for c in _mul(XYZ_TO_SRGB, xyz):
        c = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
        out.append(max(0, min(255, round(c * 255))))
    return '#%02X%02X%02X' % tuple(out)


def load_measurements():
    """paint id -> list of measurement objects (empty dict if the CSV is absent)."""
    import csv
    out = {}
    if not os.path.exists(MEASUREMENTS_PATH):
        return out
    with open(MEASUREMENTS_PATH, encoding='utf-8', newline='') as f:
        for n, r in enumerate(csv.DictReader(f), start=2):
            ill = (r.get('illuminant') or 'D50').strip()
            if ill not in WHITE:
                raise SystemExit(f"measurements.csv line {n}: unsupported illuminant {ill!r}")
            L, a, b = (float(r[k]) for k in ('L', 'a', 'b'))
            num = lambda k: int(r[k]) if (r.get(k) or '').strip().isdigit() else None
            m = OrderedDict()
            m["device"] = r['device'].strip()
            m["illuminant"] = ill
            m["observer"] = (r.get('observer') or '2').strip()
            m["lab"] = {"l": L, "a": a, "b": b}
            m["hex"] = lab_to_hex(L, a, b, ill)
            m["deviceHex"] = (r.get('device_hex') or '').strip().upper() or None
            m["samples"] = num('samples')
            m["substrate"] = (r.get('substrate') or '').strip() or None
            m["coats"] = num('coats')
            m["date"] = (r.get('date') or '').strip() or None
            m["by"] = (r.get('by') or '').strip() or None
            m["note"] = (r.get('note') or '').strip() or None
            out.setdefault(r['paint_id'].strip(), []).append((n, r, m))
    return out


def attach_measurements(brands, measurements):
    by_id = {p["id"]: (stem, p) for stem, b in brands.items() for p in b["paints"]}
    for pid, items in measurements.items():
        if pid not in by_id:
            raise SystemExit(f"measurements.csv line {items[0][0]}: unknown paint id {pid!r}")
        stem, p = by_id[pid]
        for n, r, _ in items:
            if (r.get('name') or '').strip() and r['name'].strip() != p["name"]:
                raise SystemExit(f"measurements.csv line {n}: {pid} is {p['name']!r}, "
                                 f"not {r['name'].strip()!r}")
        ms = [m for _, _, m in items]
        p["measurements"] = ms
        # Average the Lab readings when they share an illuminant; otherwise fall
        # back to the first reading rather than mixing white points.
        if len({m["illuminant"] for m in ms}) == 1:
            avg = [sum(m["lab"][k] for m in ms) / len(ms) for k in "lab"]
            p["measuredHex"] = lab_to_hex(*avg, ms[0]["illuminant"])
        else:
            p["measuredHex"] = ms[0]["hex"]


def build():
    brands = OrderedDict()
    total = 0
    for path in sorted(glob.glob(os.path.join(PAINTS_DIR, '*.md'))):
        stem = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding='utf-8') as f:
            lines = f.read().split('\n')
        lines = [l.rstrip('\r') for l in lines]

        display = next((fix(l[2:].strip()) for l in lines if l.startswith('# ')), stem)
        details = parse_details(lines)
        paints = parse_paints(lines, slug(stem))

        brand = OrderedDict()
        brand["displayName"] = display
        brand["company"] = ""
        brand["address"] = {"street": "", "city": "", "postcode": "", "country": ""}
        brand["contactEmail"] = ""
        brand["contactForm"] = ""
        brand["website"] = ""
        brand["phone"] = ""
        brand["updatedCatalogueRequested"] = ""
        for field, (group, key) in DETAIL_MAP.items():
            val = details.get(field, "")
            if group is None:
                brand[key] = val
            else:
                brand[group][key] = val
        brand["paintCount"] = len(paints)
        brand["paints"] = paints

        brands[stem] = brand
        total += len(paints)

    attach_measurements(brands, load_measurements())

    doc = OrderedDict()
    doc["$schema"] = AGG_SCHEMA_REF
    doc["schema"] = SCHEMA_VERSION
    doc["brandCount"] = len(brands)
    doc["paintCount"] = total
    doc["brands"] = brands
    return doc


def main():
    doc = build()
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write('\n')
    # Per-brand files, serialized from the same brand objects as the aggregate
    # (so json/<stem>.json can never drift from brands.<stem> in paints.json). Each
    # standalone file is prefixed with $schema/schema so it is self-identifying; the
    # embedded copies inside paints.json stay clean (the aggregate carries those keys).
    os.makedirs(JSON_DIR, exist_ok=True)
    for stem, brand in doc["brands"].items():
        out = OrderedDict()
        out["$schema"] = BRAND_SCHEMA_REF
        out["schema"] = SCHEMA_VERSION
        out.update(brand)
        with open(os.path.join(JSON_DIR, f"{stem}.json"), 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
            f.write('\n')
    print(f"Wrote {OUT_PATH} and {len(doc['brands'])} files in {JSON_DIR}: "
          f"{doc['brandCount']} brands, {doc['paintCount']} paints")


if __name__ == "__main__":
    main()
