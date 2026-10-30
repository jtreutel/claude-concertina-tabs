# claude-concertina-tabs

A [Claude](https://claude.com/claude-code) skill that arranges music for a
30-button C/G **anglo concertina** and engraves it as button tablature (a PDF).
It supports both the **Jeffries** (default) and **Wheatstone** accidental-row
layouts.

The anglo is bisonoric: each button gives one note on the push and a different
note on the pull, and both hands share one bellows. So every note that sounds at
the same instant must agree on bellows direction. That one constraint drives the
whole arrangement, which is why the skill uses a solver, not a lookup table.

## What it does

- Reads a MIDI file and picks the melody (the highest sounding pitch).
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
        --layout jeffries \
        --sections "A1:0,A2:8,B1:16,B2:24"
```

Pass `--layout wheatstone` for a Wheatstone or Lachenal instrument. The default is
`jeffries`.

A good run reports `melody mismatches: 0` and `accompaniment above the melody: 0`.

## Notes and limits

- **Input is MIDI only.** Track 0 is the melody; every other note becomes the
  accompaniment pool. MusicXML is not supported yet.
- The instrument is a C/G 30-button layout, Jeffries or Wheatstone. The Jeffries
  charts in `SKILL.md` are verified against a real instrument; the Wheatstone
  accidental row is transcribed from a published chart (note names exact, octaves
  from the standard register — verify against your box).
- The scoring weights are tuned for one piece, and the engraver has no pickup-bar
  handling yet. See "Known gaps" in `SKILL.md`.

## License

MIT. See [`LICENSE`](LICENSE).
