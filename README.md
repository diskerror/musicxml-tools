# musicxml-tools

Python utilities for working with MusicXML files.

## strip_musicxml.py

Strips visual/layout noise from MusicXML files and optionally converts them
to a compact, analysis-friendly JSON format.

Notation software exports (Sibelius, Finale, MuseScore, etc.) embed enormous
amounts of rendering data — pixel positions, font specs, colors, page
dimensions — that have nothing to do with the music. This script removes that
noise, leaving only musically meaningful content.

### Output formats

Output format is determined by the **output file extension**:

| Extension | Output |
|---|---|
| `.musicxml` / `.xml` | Stripped MusicXML |
| `.json` | Compact JSON |

### Usage

```bash
# Strip to clean MusicXML (overwrites input)
python strip_musicxml.py input.musicxml

# Strip to a new MusicXML file
python strip_musicxml.py input.musicxml output_stripped.musicxml

# Convert to compact JSON (also accepts .mxl compressed input)
python strip_musicxml.py input.musicxml output.json
python strip_musicxml.py input.mxl output.json

# Pretty-print either format
python strip_musicxml.py input.musicxml output.json --pretty
python strip_musicxml.py input.musicxml output.musicxml --pretty
```

Both `.musicxml` and `.mxl` (compressed MusicXML) are accepted as input.
The `.mxl` file is decompressed transparently in memory — no temp files.

### Stripped MusicXML

**Removes:**
- `color` attributes (present on nearly every note in Sibelius exports)
- `default-x` / `default-y` pixel positions
- Font specifications (`font-family`, `font-size`, `font-style`, etc.)
- Page and system layout elements (`page-layout`, `system-layout`, `staff-layout`)
- Visual appearance settings (`appearance`, `credit` text boxes, `print` directives)

**Keeps everything musical:**
- All notes (pitch, duration, type, voice, staff)
- Key and time signatures
- Dynamics, articulations, ornaments
- Slurs, ties, tuplets
- Tempo markings
- Measure structure

Typical size reduction: **40–60%** smaller than the original export.

### Compact JSON

Converts the score to a minimal JSON structure optimized for programmatic
analysis. A one-line schema comment at the top of every file makes the
structure self-documenting for both humans and AI tools.

**Example (pretty-printed):**
```json
{
  "_schema": "measures[]{number, key_fifths?, time?, tempo?, dynamics[]?, directions[]?, notes[]{voice, staff, pitch|'rest', type, dots?, chord?, tie?, grace?, artic[]?, ornament[]?, slur?, tuplet?}}",
  "title": "II. Largo",
  "composer": "Antonín Dvořák",
  "arranger": "Reid Woodbury Jr.",
  "measures": [
    {
      "number": 1,
      "key_fifths": -5,
      "time": "4/4",
      "tempo": 50,
      "dynamics": ["pp"],
      "notes": [
        {"voice": 1, "staff": 1, "pitch": "G#3", "type": "half"},
        {"staff": 1, "pitch": "B3", "type": "half", "chord": true},
        ...
      ]
    }
  ]
}
```

Keys marked `?` in the schema are optional and omitted when not present.
Chord notes (sounding simultaneously with the previous note) carry
`"chord": true`. Voices are numbered per-part: voices 1–4 on staff 1,
voices 5–8 on staff 2.

Typical size reduction: **85%** smaller than the original export.

## Requirements

- Python 3.9+
- No third-party dependencies (standard library only)

## Authors

- **Reid Woodbury Jr.** — score reduction, design, and domain requirements
- **Hal** (Claude Sonnet, via [OpenClaw](https://openclaw.ai)) — implementation
