# Merge notes (2026-11-01)

This fork combines the maintained forks of [Arcturus5404/miniature-paints](https://github.com/Arcturus5404/miniature-paints),
which has not been updated since March 2025.

| Fork | State at merge | Used for |
| --- | --- | --- |
| [mark-mckee](https://github.com/mark-mckee/miniature-paints) @ `9ae35e6` | 82 commits ahead; markdown in `paints/markdown/` as source of truth, JSON schema v4, CI build, 2026 catalogues for Vallejo, Army Painter, AK, Warhammer, P3, Revell, Turbo Dork, Liquitex, Two Thin Coats; discontinued paints moved out | **Base** (git history kept) |
| [bart-kooi](https://github.com/bart-kooi/miniature-paints) @ main (2026-10-27) | 31 commits ahead; original layout plus EAN column, Ammo, Warhammer Tone Pro, new Golden, RAL, Warcolours rows | Data merge, see below |
| [mlitwiniuk](https://github.com/mlitwiniuk/miniature-paints) | 5 Citadel Contrast paints | Already contained in mark-mckee |
| other 9 forks | no own changes | – |

## How bart-kooi was merged

A git merge was not possible (different layout, a new column on every line), so
[`scripts/merge_forks.py`](../scripts/merge_forks.py) merged the data row by row.
mark-mckee's values win wherever both forks have one; bart-kooi changed no hex value of an existing paint anyway.

| | Rows |
| --- | ---: |
| bart rows matched to a paint here (code / name+set / unique name / name+hex) | 7,073 / 2,872 / 438 / 34 |
| paints that received EAN codes from a matched row | 6,904 |
| codes filled in where this tree had none (Scale75 `SC-xx`, two Liquitex) | 360 |
| new paints appended | 926 |
| bart rows for paints mark-mckee had culled (discontinued / rebuilt catalogues), **not** re-added | 1,191 |
| ambiguous, left alone (EAN not transferred) | 473 |

New paints: Mig +360 (Ammo IONIC, Cobra Motor, DIO Drybrush, Shader and further Acrylics),
Warcolours +358 (Nostalgia '88/'94/'98/Rackham, Drybrush, Antithesis, Shade), Warhammer Colour +150 (Tone Pro, with a new Code column),
Golden +35, RAL +23.

Per-file details and every ambiguous case: [`merge-report-bart-kooi.json`](merge-report-bart-kooi.json).

Known gaps:
- **Revell**: mark-mckee rebuilt Revell with different names, so bart's EANs could not be matched (62 ambiguous, 145 no match).
- **Scale75**: the new Code column changes the generated ids from `scale75-<name>` to `scale75-<code>`.
- bart's `pending/paints.json` (entries without colour values) and logo updates were not taken.

## Schema v5

- `ean`: barcode list per paint (also a new `EAN` column in every markdown table).
- `measurements` / `measuredHex`: instrument readings from [`measurements/`](../measurements/README.md).
