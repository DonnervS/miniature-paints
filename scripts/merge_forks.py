#!/usr/bin/env python3
"""One-off merge: fold the bart-kooi/miniature-paints fork into this tree.

This repository is based on mark-mckee/miniature-paints (markdown in paints/markdown/
is the single source of truth). bart-kooi kept the original Arcturus5404 layout
(paints/<Brand>.md) and added an EAN column plus new paints. A git merge would
conflict on nearly every line, so this script merges the data instead.

Rules (mark-mckee's data wins wherever both have a value):
  * hex/RGB/name/set of existing rows are never changed;
  * EAN codes from bart are attached to the matching row here (new EAN column);
  * a missing manufacturer code is filled from bart (Code column added if needed);
  * rows bart added (not present upstream) and not found here are appended;
  * rows bart only inherited from upstream but that are missing here were culled
    on purpose (discontinued, rebuilt catalogue) and are NOT re-added.

Matching bart row -> row here: unique code, else name with a compatible set (set
renames are learned from code matches), else unique name on both sides, else name
plus identical hex. Anything ambiguous is left alone and listed in the report.

Needs the git remotes `upstream` (Arcturus5404), `bart` (bart-kooi) fetched:
    python scripts/merge_forks.py            # writes paints/markdown, prints report
"""
import os, re, subprocess, collections, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MD_DIR = os.path.join(ROOT, "paints", "markdown")
HEX_RE = re.compile(r'#([0-9A-Fa-f]{6})')

# bart file -> file here (renamed / merged brands)
TARGET = {
    'Citadel_Colour.md': 'Warhammer_Colour.md',
    'Warhammer.md': 'Warhammer_Colour.md',   # Tone Pro range
    'Ammo.md': 'Mig.md',                     # full AMMO by Mig catalogue
    'AKRC.md': 'AK.md',                      # Real Colors merged into AK here
}


def git_show(ref, path):
    r = subprocess.run(['git', '-C', ROOT, 'show', f'{ref}:{path}'], capture_output=True)
    return r.stdout.decode('utf-8') if r.returncode == 0 else None


def cells(line):
    return [c.strip() for c in line.split('|')[1:-1]]


def norm(s):
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())


def hexes(cell):
    return tuple(dict.fromkeys('#' + h.upper() for h in HEX_RE.findall(cell or '')))


def split_ean(s):
    return [e.strip() for e in re.split(r'[,;/\s]+', s or '') if e.strip()]


class Table:
    """The paint table of one markdown file, editable in place."""

    def __init__(self, text):
        self.lines = [l.rstrip('\r') for l in text.split('\n')]
        self.hi = next(i for i, l in enumerate(self.lines)
                       if l.startswith('|') and 'Name' in l and 'Hex' in l)
        self.header = cells(self.lines[self.hi])
        end = self.hi + 2
        while end < len(self.lines) and self.lines[end].startswith('|'):
            end += 1
        self.end = end
        self.rows = [cells(l) for l in self.lines[self.hi + 2:end] if any(cells(l))]

    def get(self, row, col):
        return row[self.header.index(col)] if col in self.header else ''

    def set(self, row, col, val):
        row[self.header.index(col)] = val

    def add_column(self, name, after):
        pos = self.header.index(after) + 1
        self.header.insert(pos, name)
        for r in self.rows:
            r.insert(pos, '')

    def dict(self, row):
        d = dict(zip(self.header, row))
        d['_hex'] = hexes(d.get('Hex', ''))
        return d

    def render(self):
        def line(c):
            return '|' + '|'.join(c) + '|'
        body = [line(self.header), line(['---'] * len(self.header))] + [line(r) for r in self.rows]
        return '\n'.join(self.lines[:self.hi] + body + self.lines[self.end:])


def parse_rows(text):
    if text is None:
        return []
    t = Table(text)
    return [t.dict(r) for r in t.rows]


def is_sorted_by_name(t):
    names = [t.get(r, 'Name').casefold() for r in t.rows]
    return names == sorted(names)


def merge_target(target, sources, report):
    path = os.path.join(MD_DIR, target)
    with open(path, encoding='utf-8') as f:
        t = Table(f.read())
    was_sorted = is_sorted_by_name(t)
    mine = [t.dict(r) for r in t.rows]

    by_code = collections.defaultdict(list)
    by_name = collections.defaultdict(list)
    for i, d in enumerate(mine):
        if norm(d.get('Code')):
            by_code[norm(d.get('Code'))].append(i)
        by_name[norm(d.get('Name'))].append(i)

    ean_for = collections.defaultdict(list)    # row index -> EANs
    code_for = {}                              # row index -> code from bart
    to_add = []
    stats = collections.Counter()
    ambiguous = []

    for src in sources:
        bart = parse_rows(git_show('bart/main', 'paints/' + src))
        up = parse_rows(git_show('upstream/main', 'paints/' + src))
        up_codes = {norm(d.get('Code')) for d in up if norm(d.get('Code'))}
        up_keys = {(norm(d.get('Name')), d['_hex']) for d in up}
        bart_name_count = collections.Counter(norm(d.get('Name')) for d in bart)

        # learn set renames from code matches
        votes = collections.defaultdict(collections.Counter)
        for d in bart:
            c = by_code.get(norm(d.get('Code')), []) if norm(d.get('Code')) else []
            if len(c) == 1:
                votes[norm(d.get('Set'))][mine[c[0]].get('Set', '')] += 1
        setmap = {}
        for bs, cnt in votes.items():
            ms, n = cnt.most_common(1)[0]
            if n / sum(cnt.values()) >= 0.6:
                setmap[bs] = ms

        def compatible(d, m):
            return (norm(m.get('Set')) == norm(d.get('Set'))
                    or norm(m.get('Set')) == norm(setmap.get(norm(d.get('Set')))))

        for d in bart:
            code = norm(d.get('Code'))
            idx, how = None, None
            c = by_code.get(code, []) if code else []
            if len(c) == 1:
                idx, how = c[0], 'code'
            else:
                cand = by_name.get(norm(d.get('Name')), [])
                comp = [i for i in cand if compatible(d, mine[i])]
                same_hex = [i for i in cand if mine[i]['_hex'] == d['_hex']]
                if len(comp) == 1:
                    idx, how = comp[0], 'name+set'
                elif (len(cand) == 1 and bart_name_count[norm(d.get('Name'))] == 1
                      and 'discontinued' not in (d.get('Set') or '').lower()):
                    idx, how = cand[0], 'unique name'
                elif len(same_hex) == 1:
                    idx, how = same_hex[0], 'name+hex'
                elif cand:
                    how = 'ambiguous'

            is_new = not ((code and code in up_codes)
                          or (norm(d.get('Name')), d['_hex']) in up_keys)

            if idx is not None:
                stats['matched by ' + how] += 1
                for e in split_ean(d.get('EAN')):
                    if e not in ean_for[idx]:
                        ean_for[idx].append(e)
                if d.get('Code') and d['Code'].lower() != 'null' and not norm(mine[idx].get('Code')):
                    code_for[idx] = d['Code']
            elif is_new:
                stats['added'] += 1
                to_add.append((d, setmap.get(norm(d.get('Set')), d.get('Set', ''))))
                if how == 'ambiguous':
                    ambiguous.append(f"{src}: added '{d.get('Name')}' ({d.get('Set')}) although "
                                     f"the name exists here in another set")
            else:
                stats['culled here, not re-added' if how != 'ambiguous' else 'ambiguous, skipped'] += 1
                if how == 'ambiguous':
                    ambiguous.append(f"{src}: '{d.get('Name')}' ({d.get('Set')}) ambiguous, EAN not transferred")

    # columns
    need_code = bool(code_for) or any(d.get('Code') and d['Code'].lower() != 'null' for d, _ in to_add)
    if need_code and 'Code' not in t.header:
        t.add_column('Code', 'Name')
    if 'EAN' not in t.header:
        t.add_column('EAN', 'Code' if 'Code' in t.header else 'Name')

    for i, eans in ean_for.items():
        t.set(t.rows[i], 'EAN', ', '.join(eans))
    for i, code in code_for.items():
        t.set(t.rows[i], 'Code', code)

    for d, setv in to_add:
        row = []
        for col in t.header:
            if col == 'Set':
                row.append(setv)
            elif col == 'EAN':
                row.append(', '.join(split_ean(d.get('EAN'))))
            elif col == 'Code':
                c = d.get('Code', '')
                row.append('' if c.lower() == 'null' else c)
            elif col in ('Name', 'R', 'G', 'B', 'Hex'):
                row.append(d.get(col, ''))
            else:
                row.append('')
        t.rows.append(row)

    if was_sorted:
        t.rows.sort(key=lambda r: t.get(r, 'Name').casefold())

    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(t.render())

    report[target] = {
        'sources': sources,
        'ean_rows': len(ean_for),
        'codes_filled': len(code_for),
        **stats,
        'ambiguous': ambiguous,
    }


def add_empty_ean_column(path):
    with open(path, encoding='utf-8') as f:
        t = Table(f.read())
    if 'EAN' in t.header:
        return
    t.add_column('EAN', 'Code' if 'Code' in t.header else 'Name')
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(t.render())


def main():
    bart_files = subprocess.run(['git', '-C', ROOT, 'ls-tree', '--name-only', 'bart/main', 'paints/'],
                                capture_output=True, text=True).stdout.split()
    groups = collections.defaultdict(list)
    for p in bart_files:
        if not p.endswith('.md'):
            continue
        src = p.split('/')[-1]
        tgt = TARGET.get(src, src)
        if os.path.exists(os.path.join(MD_DIR, tgt)):
            groups[tgt].append(src)
        else:
            print(f"!! no target for {src}")

    report = {}
    for tgt, srcs in sorted(groups.items()):
        merge_target(tgt, srcs, report)
    for name in sorted(os.listdir(MD_DIR)):
        if name.endswith('.md'):
            add_empty_ean_column(os.path.join(MD_DIR, name))

    out = os.path.join(ROOT, 'docs', 'merge-report-bart-kooi.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    for tgt, r in report.items():
        print(tgt, {k: v for k, v in r.items() if k not in ('ambiguous', 'sources')},
              f"ambiguous={len(r['ambiguous'])}")


if __name__ == '__main__':
    main()
