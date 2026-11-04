#!/usr/bin/env python3
"""Regression tests for anglotab.

    python3 tests/test_regression.py                      # synthetic checks only
    python3 tests/test_regression.py path/to/mystery.mid  # + the golden fixture

WHY A FIXTURE AND NOT JUST METRICS.  A previous rewrite of this arranger looked
fine on every aggregate measure -- melody exact, pitch classes retained within
1%, nothing above the melody -- while actually relabelling an alto line as bass,
dropping it an octave and flipping 21 slots to the wrong bellows direction.  The
damage was a redistribution, not a net loss, so no summary statistic caught it.
Only a cell-for-cell diff against a known-good arrangement did.  Keep it.
"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import anglotab as at

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []
def check(name, cond, detail=''):
    print('%-52s %s' % (name, 'ok' if cond else 'FAIL'))
    if not cond:
        fails.append(name + ((': ' + detail) if detail else ''))

# ---------------------------------------------------------------- synthetic
def note(bar, beat, dur, pitch): return ((bar*4 + beat - 1), dur, pitch)
M = at.m
# four-part D minor: melody with a held note, plus a stepwise alto run beneath it
melody = [note(0,1,1,M('D',5)), note(0,2,1,M('F',5)), note(0,3,2,M('A',5)),
          note(1,1,3,M('A',5)), note(1,4,1,M('G',5))]
alto   = [note(1,1,.5,M('C',5)), note(1,1.5,.5,M('D',5)),
          note(1,2,.5,M('E',5)), note(1,2.5,.5,M('F',5))]
tenor  = [note(0,1,4,M('A',4)), note(1,1,4,M('A',4))]
bass   = [note(0,1,4,M('D',4)), note(1,1,4,M('D',4))]
grid, mel, msound, changed, stats = at.arrange(melody, [bass, tenor, alto], 2)

bad = [i for i in range(16)
       if mel[i] is not None
       and mel[i] not in [at.RB[x][grid[i//8][i%8]['d']] for x in grid[i//8][i%8]['R']]]
check('synthetic: melody realised exactly', not bad, str(bad))

above = [(b, e) for b in range(2) for e in range(8) for x in grid[b][e]['L']
         if msound[b*8+e] and at.LB[x][grid[b][e]['d']] > msound[b*8+e]]
check('synthetic: nothing sounds above the melody', not above, str(above))

# the alto run must come out at written pitch, in whichever hand
run = [M('C',5), M('D',5), M('E',5), M('F',5)]
placed = []
for e in range(8):
    c = grid[1][e]; d = c['d']
    placed += [at.RB[x][d] for x in c['R']] + [at.LB[x][d] for x in c['L']]
got = [p for p in run if p in placed]
check('synthetic: stepwise alto run keeps its octave', len(got) >= 3,
      'placed %s of %s' % ([at.nm(p) for p in got], [at.nm(p) for p in run]))

lowest = [at.LB[x][grid[b][e]['d']] for b in range(2) for e in range(8) for x in grid[b][e]['L']]
check('synthetic: bass never placed above its written pitch',
      lowest and max(lowest) <= M('E',5), at.nm(max(lowest)) if lowest else 'no left hand')

# D minor cannot drop its tonic bass -- there is no D below D4 on a C/G -- so the
# low-octave rule is checked on a phrase whose bass note the instrument does have low.
mel2  = [note(0,1,2,M('E',5)), note(0,3,2,M('G',5))]
ten2  = [note(0,1,4,M('E',4))]
bass2 = [note(0,1,4,M('C',4))]
g2, _, ms2, _, _ = at.arrange(mel2, [bass2, ten2], 1)
low2 = [at.LB[x][g2[0][e]['d']] for e in range(8) for x in g2[0][e]['L']]
check('synthetic: a C bass is taken down to C3', low2 and min(low2) == M('C',3),
      at.nm(min(low2)) if low2 else 'no left hand at all')

# Inverted chords.  detect_chords used to read the root off the accompaniment's
# lowest downbeat note, so a C major triad over an E bass came back as E minor
# and B(dim)/D as D minor.  In a minor key that mistake is systematic -- every
# first-inversion major triad becomes the minor triad a third below -- and it
# turned a whole chart minor before anyone heard it.  Both bars below are in A
# minor, so the wrong answer is diatonic and will not stand out on its own.
inv_mel = [note(0,1,4,M('G',5)), note(0,5,4,M('E',5)),
           note(1,1,4,M('G',5)), note(1,5,4,M('B',5))]
inv_acc = [[note(0,1,2,M('E',4)), note(0,3,2,M('E',4)),          # C/E
            note(1,1,2,M('D',4)), note(1,3,2,M('D',4))],         # G/D
           [note(0,1,2,M('G',4)), note(0,3,2,M('G',4)),
            note(1,1,2,M('G',4)), note(1,3,2,M('G',4))],
           [note(0,1,2,M('C',5)), note(0,3,2,M('C',5)),
            note(1,1,2,M('B',4)), note(1,3,2,M('B',4))]]
ch = at.detect_chords([inv_mel] + inv_acc, inv_acc, 2, 4, key=(M('A',4) % 12, 'm'))
check('synthetic: C over an E bass is C, not E minor', ch[0] == (M('C',4) % 12, ''),
      'got %s%s' % (at.NM[ch[0][0]], ch[0][1]))
check('synthetic: G over a D bass is G, not D minor', ch[4] == (M('G',4) % 12, ''),
      'got %s%s' % (at.NM[ch[4][0]], ch[4][1]))

# The waltz chord must sit just above its own bass, not in a fixed register:
# pinned to C4-B4, an E minor chord put G and B up at G4 and B4, two octaves
# over the E3 bass and inside the melody's range.
fv = at.fakebook_voices([(M('E',4) % 12, 'm')]*3, 1, 3)
tones = sorted({p for v in fv for _, _, p in v})
check('synthetic: a waltz chord stays within a tenth of its bass',
      tones and tones[-1] - tones[0] <= 16, ' '.join(at.nm(p) for p in tones))
# ...and nothing narrower than a fifth down at the bottom: E3-G3-B3 growls.
check('synthetic: a low bass carries an open fifth, not a third',
      len(tones) > 1 and tones[1] - tones[0] >= 7, ' '.join(at.nm(p) for p in tones))
# A G3 bass is high enough for the ordinary G-B-D shape, which must survive.
gv = sorted({p for v in at.fakebook_voices([(M('G',4) % 12, '')]*3, 1, 3) for _, _, p in v})
check('synthetic: the plain G3-B3-D4 chord is left alone',
      gv == [M('G',3), M('B',3), M('D',4)], ' '.join(at.nm(p) for p in gv))

# ------------------------------------------------------------ golden fixture
midi = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('ANGLOTAB_FIXTURE_MIDI')
expected_path = os.path.join(HERE, 'expected_mystery.json')
if not midi:
    print('\nskipped: golden fixture needs the source MIDI.')
    print('  python3 tests/test_regression.py path/to/mystery.mid')
elif not os.path.exists(expected_path):
    print('\nskipped: %s is missing' % expected_path)
else:
    expected = json.load(open(expected_path))
    grid, mel, msound, changed, stats, voices, mel_tr, bars, how, spb, _ = at.build(midi, 32, 0)
    check('fixture: tracks read as one voice each', how == 'one voice per track', how)
    KEYS = ('d', 'R', 'L', 'M', 're')      # ignore fields added after the fixture was blessed
    def musical(c): return {k: c[k] for k in KEYS}
    diff = [(b+1, 1+e/2) for b in range(32) for e in range(8)
            if musical(grid[b][e]) != musical(expected[b][e])]
    check('fixture: reproduces the approved arrangement', not diff,
          '%d of 256 cells differ, first: %s' % (len(diff), diff[:8]))
    dirs_differ = sum(1 for b in range(32) for e in range(8)
                      if grid[b][e]['d'] != expected[b][e]['d'])
    check('fixture: every bellows direction matches', dirs_differ == 0,
          '%d slots differ' % dirs_differ)

print()
if fails:
    print('%d FAILED' % len(fails))
    for f in fails: print('  - ' + f)
    sys.exit(1)
print('all checks passed')
