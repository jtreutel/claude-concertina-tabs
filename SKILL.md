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

Before changing anything in the arranger, run the tests:

```
python3 tests/test_regression.py path/to/mystery.mid
```

### Flags that matter

| flag | why |
|---|---|
| `--beats N` | Beats per bar. **Trust the tune, not the file's time signature.** A waltz exported as 6/4 needs `--beats 3`; the grid is `beats*2` eighth slots. |
| `--transpose N` | Semitones. Run the sweep below before committing to a key. |
| `--straight` | Quantize onto a straight eighth grid: collapses rolled chords and strips ornaments. Use for anything transcribed from piano. |
| `--fakebook` | Melody plus a plain waltz/oompah accompaniment from a detected chord chart, instead of the source's own inner voices. |
| `--chords "..."` | Override the detected chart. Always offer this — chord detection is the weakest component. |
| `--melody-both-hands` | Let the melody dip into the left hand where the right cannot reach. Needed whenever the tune goes below B4. |

### Choose the key by sweeping, not by theory

Transposition changes playability enormously and not in the direction intuition
suggests. Sweep all twelve and read the numbers:

```
for t in $(seq 0 11); do
  python3 scripts/anglotab.py tune.mid --transpose $t --beats 3 -o /tmp/x.pdf \
    | grep -E 'mismatch|left hand|chord notes lost|slots missing'
done
```

Pick on `melody mismatches` first (0 or nothing else matters), then melody notes
forced into the left hand, chord notes lost, and missing pitch classes. On a C/G
the winner is usually a key with few accidentals, but which one is not
predictable — the Pokémon waltz went from unplayable to flawless at +3.

**Do not** score keys by counting accidental-row buttons. That metric is
meaningless on a Jeffries: the accidental row mostly supplies *natural* notes in
the opposite bellows direction, so heavy use of it says nothing about difficulty.
This was tried and had to be thrown out.

## Voices are the point

The rules that matter are per-voice. The bass gets dropped an octave; inner
voices never do. So the arranger has to know which line is which.

Infer voices from "the lowest note attacking at this instant" and you will label
an alto note as the bass the moment the real bass is sustaining rather than
re-attacking. It then gets the low-octave treatment and the inner line is
wrecked. This is not hypothetical — a rewrite of this tool did exactly that, and
in one bar it turned an alto walk-up of C5–D5–E5 into C4–D4–E4:

| beat | lowest note attacking | what it actually was |
|---|---|---|
| 1.5 | C5 | alto |
| 2 | D5 | alto |
| 2.5 | E5 | alto |

So: **one voice per track** wherever the source gives that, which is the normal
case for consort scores, four-part hymns and anything exported per-part.
`is_chordal()` decides, by notes-per-onset — a single line scores exactly 1.0, a
chordal keyboard track 1.5 and up. Only genuinely chordal tracks go through
`split_polyphonic()`, which ranks each note against everything **sounding** at
its onset rather than against the other onsets, so an alto entering over a held
bass is still the alto.

## Fakebook mode

For a piano transcription, the source's own accompaniment is usually the wrong
thing to transfer: rolled chords, delayed eighths and sixteenth filigree all
belong to the keyboard, not to a concertina. `--fakebook` throws it away and
rebuilds melody-plus-chords. Three rules, each learned the hard way.

**Never read the chord root off the bass note.** Detection used to take the
accompaniment's lowest note on the downbeat, on the theory that written-out
accompaniments put the root there. They do not — accompaniments invert
constantly. C major over an E bass came back as E minor, G/B as B minor, B°/D as
D minor. In a minor key the error is *systematic*: every first-inversion major
triad becomes the minor triad a third below, so the whole chart turns minor while
staying diatonic and therefore looking perfectly plausible on the page. Score
every triad against the bar's whole pitch content instead, weighted by sounding
duration, with the accompaniment at full weight and the melody at half so passing
tones cannot outvote the chord beneath them. The bass earns a bonus toward being
the root; it does not get to decide.

**Voice the chord above its own bass, never in a fixed register.** Pinning chord
tones to a fixed C4–B4 put an E minor chord's G and B at G4 and B4 — nearly two
octaves above its E3 bass, inside the melody's range, muddying the tune and
spilling into the right-hand row. Place them in the octave starting just above
the bass note.

**And keep an open fifth at the bottom.** Stacking the chord directly on a low
bass gives root position in the instrument's muddiest octave: E3–G3–B3 growls,
because of the minor third sitting at E3. When the bass is below G3 and the
nearest chord tone is less than a fifth above it, lift that tone an octave —
E3–B3–G4 instead. Above G3 a third at the bottom is fine, so the ordinary
G3–B3–D4 shape must survive untouched. (C3–G3–E4 was always right by accident:
the fifth happened to fall lower than the third.)

**Leave intro and pickup bars as written.** Bars the source does not accompany
are a figure, not a tune over chords, and stamping an oompah across them loses it
entirely. Testing only "has any accompaniment at all" is not enough: a pickup bar
whose bass walks in halfway through still gets flattened. Also pass over every
bar *before* the first one the accompaniment attacks in its own first half.
Restricting that to leading bars is what stops a mid-piece bar of sustained
harmony being mistaken for an intro.

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
| G row (6–10) | **B3 / A3** | D4 / F♯4 | G4 / A4 | B4 / C5 | D5 / E5 |

**Right hand**

| | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| accidental (1a–5a) | D♯5 / C♯5 | C♯5 / D♯5 | G♯5 / G5 | C♯6 / A♯5 | A5 / D6 |
| C row (1–5) | C5 / B4 | E5 / D5 | G5 / F5 | C6 / A5 | E6 / B5 |
| G row (6–10) | G5 / F♯5 | B5 / A5 | D6 / C6 | G6 / E6 | B6 / F♯6 |

**Left button 6 is B3 push / A3 pull.** It is bolded above because this tool
shipped with `G3 / D4` there, copied from the MuseScore anglo-tablature plugin.
That table is wrong, and demonstrably so: it also lists B3 on button 2 in *both*
its push and its pull array. The consequence was silent and nasty — A3 did not
exist on the pull at all, so every A-rooted chord on a pull quietly lost its low
root and no verification check fired. **Verify any button table against a
photograph of a real instrument's chart before trusting it**, cell by cell, and
re-bless the fixture afterwards.

The C row and G row are a fifth apart and structurally identical, so a tab read
with the rows swapped is internally consistent but sounds a fifth off. If a
player's own arrangement is the only evidence, work out which reading makes the
chords coherent: left 1 plus 4/5 pushed is C major under the C-row reading and G
major under the G-row reading — see which fits the key.

## Rules the arranger encodes

Each exists because the obvious implementation produced an audibly wrong
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
- **Put the bass in the low octave** — and only the bass. A bass part written C4–A4
  sits in the middle of the left hand; taken literally it crams every voice into
  one octave and sounds thin. Dropping it brings buttons 1, 1a, 2, 2a, 6 into play.
- **Let inner voices cross to the right hand.** On one bellows direction the left
  hand only has alternate scale degrees, so a stepwise inner run cannot live in
  one hand. Octave-displacing the missing notes destroys the line; splitting it
  across hands preserves it — a pulled C–D–E–F run goes L9, R2, L10, R3.
- **Never place an accompaniment note above the sounding melody.** Drop it instead.
- **Substitute only chord tones**, and never for an optional re-strike — just omit
  those.
- **Avoid seconds low in the texture** (within 2 semitones where the lower note is
  below G4). Muddy on a free reed.
- **Nothing narrower than a fifth at the bottom below G3.** Same reason one octave
  down: a third there growls rather than sounds.
- Prefer root position to throwing a bass note above the tenor.
- **Round half DOWN when quantizing.** Python's `round()` is banker's rounding, so
  the same ornament figure snapped to different beats in different bars. Rounding
  to nearest pushes an ornament forward onto the note it decorates; half-down
  folds it back onto the beat it belongs to.
- **Detect ornaments by raw duration, before `qd()`.** `qd()` floors at an eighth
  and so cannot see a sixteenth at all.

## Reading the verification report

- `melody mismatches` — must be 0, no exceptions. **But 0 does not mean the melody
  is complete.** It only compares notes that reached the grid; a note dropped
  during quantization is never counted. Check `notes changed from the source` and
  eyeball a few bars against the source before believing it.
- `slots missing a pitch class` — models what actually keeps sounding (a note lasts
  until the bellows turns or its button repeats) and diffs against the source.
  Catches dropped ties. A couple of dozen out of 256 is normal for a dense
  four-part source; hundreds means voices are being collapsed.
- `inner-voice notes moved to another octave` — should be in the low single
  digits. A jump here means voice identity has gone wrong.
- `accompaniment above the melody` — should be 0.
- `bellows runs` — anything past ~12 eighths is unplayable.
- `left-hand buttons used` — if the low buttons are absent the voicing has
  collapsed into one octave.
- `notes changed` — the honest list of compromises. Relay it, with the reason for
  each; players check these against the instrument.

## Testing

`tests/test_regression.py` runs synthetic checks always, and a golden-fixture
check when given the source MIDI. The synthetic checks cover melody fidelity,
octave discipline, the low-bass rule, inverted-chord detection (C/E must read as
C, G/D as G) and the waltz voicing rules. Every one of them is there because that
exact thing broke in a delivered arrangement.

When a check and the code disagree, work out which is wrong before touching
either. One of these guards was first written asserting a diminished reading of a
bar whose melody legitimately argued for the relative minor; the right fix was a
sharper test case, not a thumb on the scoring weights.

**Keep the fixture.** A rewrite of this arranger once passed every aggregate
measure — melody exact, pitch classes within 1% of the good version, nothing
above the melody — while flipping 21 of 256 slots to the wrong bellows direction
and changing 68 cells. The damage was a redistribution, not a net loss, so no
summary statistic caught it. Only `tests/expected_mystery.json`, a cell-for-cell
diff against a known-good arrangement, did.

If you change the scoring weights deliberately, re-bless the fixture with
`--dump-grid` and say so in the commit. Never re-bless to make a red test green
without listening to the result.

(`expected_mystery.json` encodes an arrangement of a specific piece. If its
provenance matters for your repo, drop it and bless your own fixture instead —
the test skips cleanly when it is absent.)

## Instrument limits worth stating plainly

- **No D below D4.** In D minor the tonic bass cannot drop an octave while C, E, F,
  G, A and B all can, so D-minor chords sit higher than everything around them.
- **No F anywhere in the left hand on the push**; no E below E5 on the pull.
- Low bass available: push C3, E3, G3, A3, B3; pull F3, G3, A3, A♯3, B3.
- The lowest note in the right hand is B4 (button 1, pull). Anything below that
  must go to the left hand, which is what `--melody-both-hands` is for.
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
  aligned, but start the staff at the first barline on systems without one.
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

- The scoring weights are tuned on one piece. The low-bass penalty of 9 in
  `slotcost()` is what forces a low walking bass rather than a mid-octave one;
  another tune may want it elsewhere. Change it and the fixture will go red —
  that is the fixture working, not failing.
- No pickup-bar handling in the engraver. The layout rules for it are above but
  unimplemented.
- MIDI input only. MusicXML would need its own parser feeding the same
  `(onset, duration, pitch)` tuples.
- `split_polyphonic` is a heuristic. On dense keyboard writing with voice
  crossing it will mislabel; check the report's octave count when using it.
- **Chord detection remains the weakest component**, even rewritten. One chord per
  bar cannot express a bar that moves (C/E for two beats then E minor), and a
  scalar accompaniment with no clear triad underneath is genuinely ambiguous —
  the same figure can score as C or as G on small weight differences. Always
  print the detected chart for the player and offer `--chords`.
- The ornament filter drops a short note only when it would land in an occupied
  slot. A lone sixteenth survives and is rounded up to a full grid step, which is
  usually right (a dotted-eighth/sixteenth scale run becomes even eighths) but
  will keep a genuine grace note that happens to sit alone.

## Reporting to the player

Lead with what changed, not with method. State melody fidelity, how much of the
accompaniment survived, then list every compromise with its cause — "no E below E5
on the pull, so the chord is in root position". A vague summary wastes their time,
because they will check it against the instrument anyway.
