# Measurements

Instrument readings of real, dried paint swatches. The hex values in `paints/markdown/` are
community approximations, mostly taken from web images and labels; a measurement is the
more reliable value when one exists.

`measurements.csv` has one row per reading. A paint may have several (different devices,
substrates or dates); `build_paints.py` attaches all of them to the paint as `measurements`
and sets `measuredHex` to the sRGB colour of their average.

| Column | Meaning |
| --- | --- |
| `paint_id` | Paint id as generated in `paints.json`, e.g. `ak-ak11057` |
| `brand`, `name` | For humans; `name` is checked against the paint id when the JSON is built |
| `device` | Instrument, e.g. `Nix Spectro 2`, `Datacolor ColorReader` |
| `illuminant`, `observer` | Reference white of the Lab values (`D50` or `D65`) and observer angle (`2` or `10`) |
| `L`, `a`, `b` | CIELAB as reported by the device |
| `device_hex` | The hex the device's app shows, kept for comparison |
| `samples` | Number of readings averaged by the device |
| `substrate` | What the paint was applied on, e.g. `white primer`, `grey primer`, `paper card` |
| `coats` | Number of coats |
| `date`, `by`, `note` | Free text |

Measure fully dried paint, opaque coverage, on a flat area larger than the sensor aperture.
The computed `hex` uses Bradford chromatic adaptation from the stated illuminant to sRGB (D65).
