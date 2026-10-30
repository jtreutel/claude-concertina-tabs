---
name: anglo-concertina-tab
description: Arrange music for a 30-button C/G Jeffries anglo concertina and engrave it as number tablature. Use for concertina arrangements, button tab, bellows-direction problems, or reading handwritten anglo tab.
---

# Anglo concertina tablature

Arranging a tune for 30-button C/G Jeffries anglo and typesetting it as button
tablature. The instrument is bisonoric: every button gives one note on the push
and a different one on the pull, and **both hands share one bellows**, so every
note sounding at a given instant must agree on direction. That single constraint
drives the whole job and is why this needs a solver rather than a lookup.

## Quick start

`scripts/anglotab.py` needs only the standard library plus `reportlab`.

```
python3 scripts/anglotab.py tune.mid -o tune.pdf --title "Tune name" \
        --sections "A1:0,A2:8,B1:16,B2:24"
```

It prints a verification report before writing the PDF. **Read the report** — it
is the part that catches real errors, and every compromise it lists should be
relayed to the player.

Tested on both a four-part consort MIDI (one voice per track) and a two-track
keyboard MIDI of the same piece: melody exact in both, zero accompaniment notes
above the melody, five notes changed out of ~270 accompaniment onsets.

## Notation

**Buttons.** Three rows per hand, numbered identically on both:

```
1a 2a 3a 4a 5a     accidental row
1  2  3  4  5      C row
6  7  8  9  10     G row
```

**Hand.** In running text, prefix `L`/`R` (`L5`, `R3a`). On an engraved sheet the
hand is the row — right hand above the divider, left below — so the number alone
is enough.

**Direction.** A line over the number means pull; bare means push. In plain text,
a leading underscore (`_R3` = pull right-hand button 3).

**Rhythm.** A grid of eighth-note slots, eight to a 4/4 or cut-time bar. A note
starts in its slot and sounds until the next one begins, so **a blank slot means
hold** and a repeated number means a re-attack. Simultaneous notes stack
vertically in one slot, in pitch order.

**Reading someone's handwritten tab:** slashes usually separate beats, not bars.
Confirm by counting tokens per group against the tune — groups of 3,3,4,3,2,2
matching quarter+two-eighths, four eighths, dotted-quarter+eighth settles it.
`X` and `-` normally mean "previous note continues".

## Button charts (C/G Jeffries, 30 button)

C4 is middle C. Each cell is **push / pull**. Verified against a real
Jeffries-layout instrument, accidental rows included.

**Left hand**

| | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| accidental (1a–5a) | E3 / F3 | A3 / A♯3 | C♯4 / D♯4 | A4 / G4 | G♯4 / A♯4 |
| C row (1–5) | C3 / G3 | G3 / B3 | C4 / D4 | E4 / F4 | G4 / A4 |
| G row (6–10) | G3 / D4 | D4 / F♯4 | G4 / A4 | B4 / C5 | D5 / E5 |

**Right hand**

| | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| accidental (1a–5a) | D♯5 / C♯5 | C♯5 / D♯5 | G♯5 / G5 | C♯6 / A♯5 | A5 / D6 |
| C row (1–5) | C5 / B4 | E5 / D5 | G5 / F5 | C6 / A5 | E6 / B5 |
| G row (6–10) | G5 / F♯5 | B5 / A5 | D6 / C6 | G6 / E6 | B6 / F♯6 |

The C row and G row are a fifth apart and structurally identical, so a tab read
with the rows swapped is internally consistent but sounds a fifth off. If a
player's own arrangement is the only evidence, work out which reading makes the
chords coherent: left 1 plus 4/5 pushed is C major under the C-row reading and G
major under the G-row reading — see which fits the key.

## Rules the script encodes

Each of these exists because the obvious implementation produced an audibly wrong
arrangement. Keep them if you rewrite it.

- **Quantize durations before testing sustain.** Sequencers write ~95% of nominal
  length; add any sustain fudge on top and releases overlap the next downbeat,
  putting every melody note one slot late.
- **Melody is the highest *sounding* pitch, not the highest onset.** In keyboard
  textures a held upper note sits above a moving inner voice for several beats.
  The melody must come out exactly — same pitch, same octave. Everything else is
  negotiable; this is not.
- **Re-strike anything cut by a bellows change.** A tie cannot survive a direction
  change — the note physically stops. Bass *and* inner voices need re-attacking,
  and a held bass also wants re-striking on each beat so the line keeps speaking.
  Missing this leaves audible holes that look fine on the page.
- **Allow the melody to re-articulate mid-note** at a penalty rather than forbidding
  direction changes under a sustained note. Those splits are idiomatic and are
  often the only route to a complete cadence chord.
- **Put the bass in the low octave.** A bass part written C4–A4 sits in the middle
  of the left hand; taken literally it crams every voice into one octave and
  sounds thin. Dropping it an octave brings buttons 1, 1a, 2, 2a, 6 into play.
- **Let inner voices cross to the right hand.** On one bellows direction the left
  hand only has alternate scale degrees, so a stepwise inner run cannot live in
  one hand. Octave-displacing the missing notes destroys the line; splitting it
  across hands preserves it — a pulled C–D–E–F run goes L9, R2, L10, R3.
- **Never place an accompaniment note above the sounding melody.** Drop it instead.
- **Substitute only chord tones**, and never for an optional re-strike — just omit
  those.
- **Avoid seconds low in the texture** (within 2 semitones where the lower note is
  below G4). Muddy on a free reed.
- Prefer root position to throwing a bass note above the tenor.

## Reading the verification report

- `melody mismatches` — must be 0, no exceptions.
- `slots missing a pitch class` — models what actually keeps sounding (a note lasts
  until the bellows changes or its button is re-struck) and diffs it against the
  source. This is what catches dropped ties. A couple of dozen out of 256 is
  normal for a dense four-part source; a number in the hundreds means voices are
  being collapsed.
- `accompaniment above the melody` — should be 0.
- `bellows runs` — anything past ~12 eighths is unplayable.
- `left-hand buttons used` — if the low buttons are absent the voicing has
  collapsed into one octave.
- `notes changed` — the honest list of compromises. Relay it, with the reason for
  each; players check these against the instrument.

## Instrument limits worth stating plainly

- **No D below D4.** In D minor the tonic bass cannot drop an octave while C, E, F,
  G, A and B all can, so D-minor chords sit higher than everything around them.
- **No F anywhere in the left hand on the push**; no E below E5 on the pull.
- Low bass available: push C3, E3, G3, A3; pull F3, G3, B3, D4.
- D minor and D dorian lie well: Dm, F and G7 on the pull of the left C row, C and
  E minor on the push, so chord changes drive the bellows instead of fighting it.
  G major behaves the same way on the G row.

## Engraving

Defaults in the script, all arrived at by correction:

- Portrait A4, one page where it fits. Four bars per system for long pieces, two
  for short ones so the numbers stay large.
- **One fixed slot width across the whole sheet**, so barlines stack vertically down
  the page and every number is centred in its own eighth slot. This is what "the
  numbers line up" means; proportional boxes per system do not.
- **Close the staff at both ends.** Horizontal rules that stop in mid-air read as a
  cut-off page. With a pickup, reserve the gutter on every system so bars stay
  aligned, but start the staff at the first barline on systems without one rather
  than leaving an empty box hanging off the front.
- **Stacks in pitch order top to bottom**, melody down through the left-hand bass.
  Inverting this is easy to do and looks wrong immediately.
- **Melody black on a fixed top line, accompaniment in a second colour** — essential
  once inner voices appear in the right-hand row.
- A dashed rule at the mid-bar beat only; dotting every quarter clutters. Small bar
  number in the margin, short section labels above.
- Title on one line, single-line subtitle with key, metre and the pull convention.
  **No explanatory paragraph** unless asked.
- Rasterize with `pdftoppm` and look at the result before sending, including a zoom
  on one system. Watch for pull overlines colliding with the staff rule and
  two-character labels (`5a`, `10`) touching barlines.

## Known gaps

- The scoring weights are tuned for one piece. The low-bass penalty of 9 in
  `cost()` is what forces a low walking bass rather than a mid-octave one; another
  tune may want it elsewhere.
- The engraver has no pickup-bar handling — the layout rules for it are written
  above but not implemented.
- MIDI input only. MusicXML would need its own parser feeding the same
  `(onset, duration, pitch)` tuples.

## Reporting to the player

Lead with what changed, not with method. State melody fidelity, how much of the
accompaniment survived, then list every compromise with its cause — "no E below E5
on the pull, so the chord is in root position". A vague summary wastes their time,
because they will check it against the instrument anyway.
