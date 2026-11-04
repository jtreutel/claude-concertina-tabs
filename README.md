# claude-concertina-tabs

A [Claude](https://claude.com/claude-code) skill that arranges music for a
30-button C/G **Jeffries anglo concertina** and engraves it as button tablature
(a PDF).

The anglo is bisonoric: each button gives one note on the push and a different
note on the pull, and both hands share one bellows. So every note that sounds at
the same instant must agree on bellows direction. That one constraint drives the
whole arrangement, which is why the skill uses a solver, not a lookup table.

## What it does

- Reads a MIDI file and picks the melody (the highest *sounding* pitch).
- Separates the accompaniment into voices, so the bass drops an octave but the
  inner lines keep theirs.
- Solves the bellows direction for every eighth-note slot.
- Fits the accompaniment under the melody, and records every compromise it makes.
- Writes a tablature PDF with the right hand above the divider and the left below.
- Prints a verification report first. **Read the report** — it catches the real
  errors and lists every change from the source.

## Layout

```
.
├── SKILL.md            # the skill: notation, button charts, rules, engraving notes
├── scripts/
│   └── anglotab.py     # the arranger and PDF engraver
├── tests/
│   ├── test_regression.py   # synthetic checks + a golden-fixture diff
│   └── expected_mystery.json
├── LICENSE
└── README.md
```

## Use as a Claude skill

Claude matches on the `name` and `description` in the `SKILL.md` frontmatter. Put
this directory where your Claude session loads skills from, then ask for a
concertina arrangement, button tab, help with a bellows-direction problem, or a
read of handwritten anglo tab.

## Run the script directly

The script needs Python 3 and [`reportlab`](https://pypi.org/project/reportlab/).
Everything else is the standard library. There is no network use and no data
files.

```bash
pip install reportlab

python3 scripts/anglotab.py tune.mid -o tune.pdf --title "Tune name" \
        --sections "A1:0,A2:8,B1:16,B2:24"
```

A good run reports `melody mismatches: 0` and `accompaniment above the melody: 0`.

Useful flags (see `SKILL.md` for the full list):

- `--transpose N` — shift every track N semitones. Transposition changes
  playability a lot, so sweep all twelve keys and read the report before you
  commit to one.
- `--beats N` — beats per bar; trust the tune, not the file's time signature.
- `--melody-both-hands` — let the melody dip into the left hand when it goes
  below B4, the lowest note the right hand reaches.
- `--fakebook` — replace the source's piano texture with melody plus a plain
  chord accompaniment.
- `--chords "Am | E | Am | Dm"` — override the detected chord chart, one symbol
  per bar. Chord detection is the weakest component, so always check it.

Run the tests before changing the arranger:

```bash
python3 tests/test_regression.py            # synthetic checks only
python3 tests/test_regression.py tune.mid   # plus the golden-fixture diff
```

## Notes and limits

- **Input is MIDI only.** The melody is the highest sounding pitch; the other
  tracks become the accompaniment, separated into voices. MusicXML is not
  supported yet.
- The instrument is a C/G 30-button Jeffries layout. The button charts in
  `SKILL.md` are verified cell-by-cell against a real instrument.
- Chord detection is the weakest component. Always read the detected chart and
  override it with `--chords` when it is wrong.
- The scoring weights are tuned for one piece, and the engraver has no pickup-bar
  handling yet. See "Known gaps" in `SKILL.md`.

## License

MIT. See [`LICENSE`](LICENSE).
