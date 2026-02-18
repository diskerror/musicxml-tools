#!/usr/bin/env python3
"""
strip_musicxml.py — Clean and convert MusicXML files for analysis.

Output format is determined by the output file's extension:
  .musicxml / .xml  →  Stripped MusicXML  (removes visual/layout noise)
  .json             →  Compact JSON        (analysis-friendly structure)

Usage:
    python strip_musicxml.py input.musicxml output.musicxml
    python strip_musicxml.py input.musicxml output.json
    python strip_musicxml.py input.musicxml output.json --pretty
    python strip_musicxml.py input.musicxml output.musicxml --pretty
    python strip_musicxml.py input.musicxml          # overwrites as stripped XML
"""

import xml.etree.ElementTree as ET
import json
import sys
import os
import argparse


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# XML attributes to strip from every element (visual rendering hints only)
STRIP_ATTRS = {
    'color',
    'default-x',
    'default-y',
    'font-family',
    'font-size',
    'font-weight',
    'font-style',
    'justify',
    'valign',
    'enclosure',
    'print-object',
}

# Top-level elements to remove entirely (page/system layout, not music)
STRIP_ELEMENTS = {
    'page-layout',
    'system-layout',
    'staff-layout',
    'appearance',
    'credit',
    'music-font',
    'word-font',
    'lyric-font',
    'lyric-language',
    'print',         # print/layout directives inside measures
}

# Alter values → accidental symbols for readable pitch names
ACCIDENTALS = {
    '2':  'x',   # double sharp
    '1':  '#',   # sharp
    '0':  '',    # natural
    '-1': 'b',   # flat
    '-2': 'bb',  # double flat
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def detag(element):
    """Strip XML namespace from a tag: '{ns}tag' → 'tag'."""
    tag = element.tag
    return tag.split('}')[-1] if '}' in tag else tag


def pitch_name(pitch_el):
    """
    Convert a MusicXML <pitch> element to a readable string like 'A#4'.
    Returns None if the element is missing.
    """
    if pitch_el is None:
        return None
    step   = pitch_el.findtext('step', '')
    alter  = pitch_el.findtext('alter', '0').strip()
    octave = pitch_el.findtext('octave', '')
    # Round alter to nearest int to handle floating-point values like '1.0'
    try:
        alter_key = str(int(round(float(alter))))
    except ValueError:
        alter_key = '0'
    acc = ACCIDENTALS.get(alter_key, '')
    return f"{step}{acc}{octave}"


def text(element, path, default=None):
    """Shorthand: find a child element and return its text, or a default."""
    el = element.find(path)
    return el.text.strip() if el is not None and el.text else default


# ---------------------------------------------------------------------------
# XML stripping
# ---------------------------------------------------------------------------

def strip_attributes(element):
    """Remove visual attributes from a single XML element in-place."""
    for attr in list(element.attrib):
        if attr in STRIP_ATTRS:
            del element.attrib[attr]


def strip_tree(parent):
    """
    Recursively walk the XML tree, stripping unwanted attributes and
    removing unwanted child elements.
    """
    to_remove = []
    for child in parent:
        tag = detag(child)
        if tag in STRIP_ELEMENTS:
            to_remove.append(child)
        else:
            strip_attributes(child)
            strip_tree(child)
    for child in to_remove:
        parent.remove(child)


def write_xml(tree, output_path, pretty):
    """Write a (stripped) ElementTree to an XML file."""
    if pretty:
        ET.indent(tree, space='  ')
    tree.write(output_path,
               encoding='UTF-8',
               xml_declaration=True,
               short_empty_elements=False)


# ---------------------------------------------------------------------------
# JSON conversion
# ---------------------------------------------------------------------------

def build_json(root):
    """
    Convert a parsed MusicXML ElementTree root into a compact dict
    suitable for JSON output.

    Structure:
        {
          "title": ...,
          "composer": ...,
          "arranger": ...,
          "measures": [
            {
              "number": 1,
              "key_fifths": -5,      # sharps (+) or flats (-), when changed
              "time": "4/4",         # when changed
              "tempo": 50,           # when changed
              "notes": [
                {
                  "voice": 1,
                  "staff": 1,
                  "pitch": "Ab4",    # or "rest"
                  "type": "quarter",
                  "dots": 1,         # if dotted
                  "chord": true,     # sounds with previous note
                  "tie": "start",    # "start", "stop", or omitted
                  "grace": true,     # if grace note
                  "artic": [...],    # articulations present
                  "dyn": "pp",       # dynamic marking, if on this note
                  "slur": "start"    # "start", "stop", or omitted
                },
                ...
              ],
              "directions": [...]    # text directions (cresc., rit., etc.)
            },
            ...
          ]
        }
    """

    # --- Score-level metadata ---
    score = {}

    # One-line schema: helps AI readers understand the structure at a glance.
    # Keys marked ? are optional (omitted when not present).
    score['_schema'] = (
        "measures[]{number, key_fifths?, time?, tempo?, dynamics[]?, wedges[]?, "
        "pedals[]?, directions[]?, "
        "notes[]{voice, staff, pitch|'rest', type, dots?, beam[]?, chord?, tie?, "
        "grace?, artic[]?, ornament[]?, slur?, tuplet?}}"
    )

    score['title']    = root.findtext('work/work-title') or \
                        root.findtext('movement-title') or None
    score['composer'] = None
    score['arranger'] = None
    for creator in root.findall('identification/creator'):
        role = creator.get('type', '')
        if role == 'composer':
            score['composer'] = creator.text
        elif role == 'arranger':
            score['arranger'] = creator.text

    score['measures'] = []

    # --- Walk measures ---
    for measure_el in root.iter('measure'):
        m = {'number': int(measure_el.get('number', 0))}

        # Key signature (when it appears)
        key_el = measure_el.find('.//key')
        if key_el is not None:
            fifths = key_el.findtext('fifths')
            if fifths is not None:
                m['key_fifths'] = int(fifths)

        # Time signature (when it appears)
        time_el = measure_el.find('.//time')
        if time_el is not None:
            beats     = time_el.findtext('beats')
            beat_type = time_el.findtext('beat-type')
            if beats and beat_type:
                m['time'] = f"{beats}/{beat_type}"

        # Tempo (from <metronome> inside a <direction>)
        for metro in measure_el.iter('metronome'):
            per_minute = metro.findtext('per-minute')
            if per_minute:
                m['tempo'] = int(float(per_minute))
                break

        # Text directions (cresc., dim., expression marks, etc.)
        directions = []
        for dir_el in measure_el.findall('direction'):
            for words_el in dir_el.findall('.//words'):
                if words_el.text:
                    directions.append(words_el.text.strip())
        if directions:
            m['directions'] = directions

        # Hairpin wedges (crescendo/diminuendo graphical markings)
        wedges = []
        for dir_el in measure_el.findall('direction'):
            for wedge_el in dir_el.findall('.//wedge'):
                w = {'type': wedge_el.get('type')}
                num = wedge_el.get('number')
                if num:
                    w['number'] = int(num)
                wedges.append(w)
        if wedges:
            m['wedges'] = wedges

        # Pedal markings
        pedals = []
        for dir_el in measure_el.findall('direction'):
            for pedal_el in dir_el.findall('.//pedal'):
                p = {'type': pedal_el.get('type')}
                line = pedal_el.get('line')
                if line:
                    p['line'] = line == 'yes'
                pedals.append(p)
        if pedals:
            m['pedals'] = pedals

        # --- Notes ---
        notes = []
        for note_el in measure_el.findall('note'):
            n = {}

            # Voice and staff
            voice = note_el.findtext('voice')
            staff = note_el.findtext('staff')
            if voice:
                n['voice'] = int(voice)
            if staff:
                n['staff'] = int(staff)

            # Pitch (or rest)
            rest_el  = note_el.find('rest')
            pitch_el = note_el.find('pitch')
            if rest_el is not None:
                n['pitch'] = 'rest'
            elif pitch_el is not None:
                n['pitch'] = pitch_name(pitch_el)

            # Duration type and dots
            ntype = note_el.findtext('type')
            if ntype:
                n['type'] = ntype
            dots = len(note_el.findall('dot'))
            if dots:
                n['dots'] = dots

            # Chord (sounds simultaneously with previous note)
            if note_el.find('chord') is not None:
                n['chord'] = True

            # Beaming (visual grouping — kept for consistency analysis)
            beams = [b.text.strip() for b in note_el.findall('beam') if b.text]
            if beams:
                n['beam'] = beams

            # Grace note
            if note_el.find('grace') is not None:
                n['grace'] = True

            # Tie
            for tie_el in note_el.findall('tie'):
                tie_type = tie_el.get('type')
                if tie_type:
                    n['tie'] = tie_type   # 'start' or 'stop'
                    break

            # Articulations
            artics = []
            for artic_el in note_el.findall('.//articulations/*'):
                artics.append(detag(artic_el))
            if artics:
                n['artic'] = artics

            # Ornaments
            ornaments = []
            for orn_el in note_el.findall('.//ornaments/*'):
                ornaments.append(detag(orn_el))
            if ornaments:
                n['ornament'] = ornaments

            # Slur
            for slur_el in note_el.findall('.//slur'):
                slur_type = slur_el.get('type')
                if slur_type:
                    n['slur'] = slur_type
                    break

            # Tuplet
            for tuplet_el in note_el.findall('.//tuplet'):
                tup_type = tuplet_el.get('type')
                if tup_type == 'start':
                    actual = note_el.findtext('.//actual-notes')
                    normal = note_el.findtext('.//normal-notes')
                    if actual and normal:
                        n['tuplet'] = f"{actual}:{normal}"
                    break

            # Dynamic marking on this note's direction (look at enclosing
            # direction elements in the measure that reference this voice)
            # — dynamics are on <direction> elements, not on notes directly,
            # so we attach them to the first note of the same voice after
            # the direction. This is a simplification.

            notes.append(n)

        # Attach dynamics to the measure rather than individual notes
        # (more accurate representation of how MusicXML stores them)
        dynamics = []
        for dir_el in measure_el.findall('direction'):
            for dyn_el in dir_el.find('.//dynamics') or []:
                dynamics.append(detag(dyn_el))
        if dynamics:
            m['dynamics'] = dynamics

        if notes:
            m['notes'] = notes

        score['measures'].append(m)

    return score


def write_json(data, output_path, pretty):
    """Write the converted data dict to a JSON file."""
    indent = 2 if pretty else None
    # separators=(',', ':') gives the most compact output when not pretty
    separators = None if pretty else (',', ':')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=indent, separators=separators,
                  ensure_ascii=False)
        f.write('\n')  # trailing newline — good practice


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description='Strip or convert MusicXML files.',
        epilog='Output format is determined by the output file extension '
               '(.xml/.musicxml → stripped XML, .json → compact JSON).'
    )
    parser.add_argument('input',
                        help='Input MusicXML file')
    parser.add_argument('output', nargs='?',
                        help='Output file (default: overwrite input as XML)')
    parser.add_argument('--pretty', action='store_true',
                        help='Pretty-print the output (XML or JSON)')
    return parser.parse_args()


def main():
    args = parse_args()

    input_path  = args.input
    output_path = args.output or input_path
    pretty      = args.pretty

    if not os.path.exists(input_path):
        print(f"Error: file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading:  {input_path}")

    tree = ET.parse(input_path)
    root = tree.getroot()

    # Determine output format from file extension
    ext = os.path.splitext(output_path)[1].lower()

    if ext == '.json':
        # --- JSON output ---
        data = build_json(root)
        write_json(data, output_path, pretty)
        fmt = 'JSON (pretty)' if pretty else 'JSON (compact)'

    else:
        # --- Stripped XML output ---
        strip_attributes(root)
        strip_tree(root)
        write_xml(tree, output_path, pretty)
        fmt = 'XML (pretty)' if pretty else 'XML (compact)'

    input_size  = os.path.getsize(input_path)
    output_size = os.path.getsize(output_path)
    reduction   = 100 * (1 - output_size / input_size)

    sign = '-' if reduction >= 0 else '+'
    pct  = abs(reduction)

    print(f"Writing:  {output_path}  [{fmt}]")
    print(f"Size:     {input_size:,} → {output_size:,} bytes  "
          f"({sign}{pct:.0f}%)")


if __name__ == '__main__':
    main()
