#!/usr/bin/env python3
"""Arrange a MIDI file for 30-button C/G Jeffries anglo concertina and engrave
button tablature as a PDF.

    python3 anglotab.py tune.mid -o tune.pdf --title "Tune name"

VOICES ARE THE POINT.  The arranger needs to know which line is the bass, which
is the tenor and so on, because the rules that matter are per-voice: the bass
gets dropped an octave, inner voices never do.  Infer that from the lowest note
sounding at each instant and you will label an alto note as bass, drop it an
octave, and wreck the inner line.  So: one voice per track where the source
gives that (consort scores, four-part hymns), and only where a track is
genuinely polyphonic does `split_polyphonic` separate it, ranking each note
against everything SOUNDING at its onset rather than against the other onsets.

Melody comes from --melody-track (default 0), as that track's top line.
Remaining tracks become accompaniment voices ordered by mean pitch, lowest
first.  Prints a verification report; read it before trusting the output.
"""
import argparse, json, math, struct, sys
from collections import Counter

# ---------------------------------------------------------------- note tables
def m(n, o):
    return {'C':0,'C#':1,'D':2,'D#':3,'E':4,'F':5,'F#':6,
            'G':7,'G#':8,'A':9,'A#':10,'B':11}[n] + 12*(o+1)
NM = ['C','C#','D','Eb','E','F','F#','G','Ab','A','Bb','B']
def nm(a): return NM[a % 12] + str(a//12 - 1)

# (push, pull).  Row numbering: 1a-5a accidentals, 1-5 C row, 6-10 G row.
LB = {'1':(m('C',3),m('G',3)),'2':(m('G',3),m('B',3)),'3':(m('C',4),m('D',4)),
      '4':(m('E',4),m('F',4)),'5':(m('G',4),m('A',4)),'6':(m('B',3),m('A',3)),
      '7':(m('D',4),m('F#',4)),'8':(m('G',4),m('A',4)),'9':(m('B',4),m('C',5)),
      '10':(m('D',5),m('E',5)),'1a':(m('E',3),m('F',3)),'2a':(m('A',3),m('A#',3)),
      '3a':(m('C#',4),m('D#',4)),'4a':(m('A',4),m('G',4)),'5a':(m('G#',4),m('A#',4))}
RB = {'1':(m('C',5),m('B',4)),'2':(m('E',5),m('D',5)),'3':(m('G',5),m('F',5)),
      '4':(m('C',6),m('A',5)),'5':(m('E',6),m('B',5)),'6':(m('G',5),m('F#',5)),
      '7':(m('B',5),m('A',5)),'8':(m('D',6),m('C',6)),'9':(m('G',6),m('E',6)),
      '10':(m('B',6),m('F#',6)),'1a':(m('D#',5),m('C#',5)),'2a':(m('C#',5),m('D#',5)),
      '3a':(m('G#',5),m('G',5)),'4a':(m('C#',6),m('A#',5)),'5a':(m('A',5),m('D',6))}
OL = ['3','4','5','7','9','1','2','8','10','6','1a','4a','2a','5a','3a']
OR = ['1','2','3','4','5','6','7','8','5a','3a','1a','2a','9','10','4a']
LOWORD = ['1','1a','2','6','2a','3','7','4','5','8','9','10','4a','5a','3a']
PUSH, PULL = 0, 1
WEIGHTS = [20, 16, 11, 8, 6]          # bass first, then upward

def bf(tbl, order, pitch, dr):
    for b in order:
        if tbl[b][dr] == pitch:
            return b
    return None

# --------------------------------------------------------------- midi parsing
def read_midi(path):
    data = open(path, 'rb').read()
    if data[:4] != b'MThd':
        sys.exit('not a MIDI file')
    _, ntr, div = struct.unpack('>HHH', data[8:14])
    def vlq(b, i):
        v = 0
        while True:
            c = b[i]; i += 1; v = (v << 7) | (c & 0x7f)
            if c < 0x80:
                return v, i
    p, tracks, beats = 14, [], 4
    for _ in range(ntr):
        ln = struct.unpack('>I', data[p+4:p+8])[0]
        buf = data[p+8:p+8+ln]; p += 8 + ln
        i = tick = 0; rs = None; on = {}; notes = []; seen_ts = False
        while i < len(buf):
            dt, i = vlq(buf, i); tick += dt; st = buf[i]
            if st == 0xff:
                ty = buf[i+1]; n, j = vlq(buf, i+2)
                if ty == 0x58 and n >= 2 and not seen_ts:
                    beats = buf[j]; seen_ts = True
                i = j + n; continue
            if st in (0xf0, 0xf7):
                n, j = vlq(buf, i+1); i = j + n; continue
            if st & 0x80:
                rs = st; i += 1
            ev = rs & 0xf0
            if ev in (0xc0, 0xd0):
                i += 1; continue
            a, vel = buf[i], buf[i+1]; i += 2
            if ev == 0x90 and vel > 0:
                on.setdefault(a, []).append(tick)
            elif ev in (0x80, 0x90) and on.get(a):
                s = on[a].pop(0); notes.append((s/div, (tick-s)/div, a))
        notes.sort()
        if notes:
            tracks.append(notes)
    return tracks, beats

def qd(du):
    """Sequencers write ~95% of nominal length; snap back to the grid.  Without
    this, releases overlap the next downbeat and every melody note lands late."""
    return max(0.5, round(du/0.95*4)/4)
def quantize(tracks, grid=0.5):
    """Snap onsets and durations onto a straight grid, for playing a piano
    transcription without its rubato.  Three passes:

    1. Collapse rolled chords.  Notes that start within one grid step of each
       other and release together are a spread chord; played straight they
       sound together, so they all take the earliest onset.  Without this a
       roll wider than half a grid step gets split across two slots.

    2. Snap, rounding half DOWN, so an ornament a sixteenth before a main note
       folds onto the beat it decorates rather than landing on the note that
       follows.  (Rounding to nearest pushes x.5 forward; Python's round() is
       banker's rounding, so the same figure snaps to different beats in
       different bars.)

    3. Where several onsets still share a slot, keep the long notes -- that is
       a chord.  If every note there is shorter than the grid it was an
       ornamental run, and only the first group survives.  This tests the RAW
       duration: qd() floors at an eighth and cannot see a sixteenth."""
    SHORT = grid * 0.8
    out = []
    for tr in tracks:
        notes = sorted(tr)
        moved = list(notes)
        for i, (s, d, p) in enumerate(notes):                   # pass 1: rolls
            for j in range(i):
                s0, d0, _ = notes[j]
                if 0 < s - s0 < grid and abs((s0+d0) - (s+d)) < 0.05:
                    moved[i] = (moved[j][0], d + (s - moved[j][0]), p)
                    break
        groups = {}
        for s, d, p in moved:                                   # pass 2: snap
            slot = math.ceil(s/grid - 0.5) * grid
            groups.setdefault(round(slot, 6), []).append((s, d, p))
        keep = {}
        for slot, items in groups.items():                      # pass 3: ornaments
            longs = [x for x in items if x[1] >= SHORT]
            if not longs:
                first = min(x[0] for x in items)
                longs = [x for x in items if abs(x[0]-first) < 1e-6]
            for _, d, p in longs:
                d2 = max(grid, math.floor(qd(d)/grid + 0.5) * grid)
                keep[(slot, p)] = max(keep.get((slot, p), 0), d2)
        out.append(sorted((s, d, p) for (s, p), d in keep.items()))
    return out

def snd(tr, t): return [a for s, du, a in tr if s - 1e-9 <= t < s + qd(du) - 1e-6]
def ons(tr, t): return [a for s, du, a in tr if abs(s - t) < 1e-6]

# ------------------------------------------------------------ voice separation
TRIADS = [(0, 4, 7, ''), (0, 3, 7, 'm'), (0, 4, 7, '7'), (0, 3, 6, 'dim')]

MAJOR_PROFILE = [6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88]

def estimate_key(tracks):
    """Krumhansl-style key fit over the whole piece, used only to prefer
    diatonic chords when the evidence in one bar is thin."""
    hist = [0.0]*12
    for tr in tracks:
        for s, d, p in tr:
            hist[p % 12] += qd(d)
    best = None
    for tonic in range(12):
        for prof, mode in ((MAJOR_PROFILE, ''), (MAJOR_PROFILE[9:]+MAJOR_PROFILE[:9], 'm')):
            sc = sum(hist[(tonic+i) % 12]*prof[i] for i in range(12))
            if best is None or sc > best[0]: best = (sc, tonic, mode)
    return best[1], best[2]

TRIADS = (('', (0, 4, 7)), ('m', (0, 3, 7)), ('dim', (0, 3, 6)))

def detect_chords(tracks, acc, bars, beats, key=None):
    """One chord per bar, by matching every triad against the bar's whole
    pitch content, weighted by how long each pitch class sounds.

    An earlier version read the root straight off the accompaniment's lowest
    note on the downbeat, on the theory that a written-out accompaniment puts
    the root there.  It does not: accompaniments invert constantly.  A bar of
    C major over an E bass (E + G + C) came back as E minor, G/B as B minor,
    B(dim)/D as D minor.  In a minor key the error is systematic -- every
    first-inversion major triad turns into the minor triad a third below --
    so the chart came out almost entirely minor and sounded wrong against the
    tune.  The bass is still good evidence about the root, so it earns a
    bonus, but it no longer decides on its own."""
    tonic, mode = key if key else estimate_key(tracks)
    scale = {(tonic+i) % 12 for i in ([0,2,4,5,7,9,11] if mode == '' else [0,2,3,5,7,8,10])}
    accid = {id(t) for t in acc}
    mel_tracks = [t for t in tracks if id(t) not in accid]
    def sounding_pcs(lo, hi, src, w, pcs=None):
        pcs = {} if pcs is None else pcs
        for tr in src:
            for s, d, p in tr:
                ov = min(hi, s+qd(d)) - max(lo, s)
                if ov > 0: pcs[p % 12] = pcs.get(p % 12, 0) + ov*w
        return pcs
    out = []
    for b in range(bars):
        lo, hi = b*beats, (b+1)*beats
        # The accompaniment carries the harmony; the melody votes at half
        # weight, so its passing tones cannot outvote the chord under them.
        pcs = sounding_pcs(lo, hi, acc, 1.0)
        sounding_pcs(lo, hi, mel_tracks, 0.5, pcs)
        if not pcs:
            out += [out[-1] if out else None]*beats; continue
        bass = min((p for tr in acc for s, d, p in tr
                    if lo - 1e-9 <= s < lo + beats*0.5), default=None)
        tot = sum(pcs.values()) or 1.0
        best = None
        for root in range(12):
            for qual, iv in TRIADS:
                tones = {(root+x) % 12 for x in iv}
                sc = sum(pcs.get(t, 0) for t in tones)
                sc -= 0.9*sum(v for k, v in pcs.items() if k not in tones)
                sc += 0.5*pcs.get(root, 0)                   # the root should sound
                if bass is not None and bass % 12 == root: sc += 0.35*tot
                if tones <= scale: sc += 0.10*tot
                if qual == 'dim': sc -= 0.15*tot             # a last resort, not a default
                if best is None or sc > best[0]: best = (sc, root, qual)
        out += [(best[1], best[2])]*beats
    return out

def bass_octave(root):
    """Lowest octave in which the left hand actually has this pitch class.  On a
    C/G there is no D below D4, so a D-rooted chord must take its root up an
    octave rather than settle for the third in the bass."""
    have = {v for pair in LB.values() for v in pair}
    for p in (36+root, 48+root, 60+root):
        if p in have: return p
    return 60 + root

def fakebook_voices(chords, bars, beats, skip=()):
    """Turn a chord chart into a plain waltz accompaniment: bass note on beat
    one, chord on the other beats.  Returned as ordinary note lists, so the
    normal arranger handles bellows direction, the low-octave bass and
    re-strikes."""
    bass, mid, top = [], [], []
    for b in range(bars*beats):
        if b // beats in skip: continue          # leave unaccompanied bars alone
        ch = chords[b] if b < len(chords) else None
        if ch is None: continue
        root, qual = ch
        third = (root + (3 if qual in ('m', 'dim') else 4)) % 12
        fifth = (root + (6 if qual == 'dim' else 7)) % 12
        bp = bass_octave(root)
        if b % beats == 0:
            bass.append((b*1.0, 1.0, bp))
        else:
            # The chord sits in the octave directly above its own bass note.
            # Pinned to a fixed C4-B4 instead, an E minor chord put its G and
            # B at G4 and B4 -- nearly two octaves over an E3 bass, up in the
            # melody's register, where it muddied the tune and spilled into
            # the right hand.
            floor = max(m('G', 3), bp + 2)
            place = lambda pc: floor + (pc - floor) % 12
            tp, fp = place(third), place(fifth)
            # Nothing narrower than a fifth sits at the bottom of the bass
            # octave.  An E3 bass with its own G3 and B3 stacked straight on
            # top is a root-position triad crushed into the instrument's
            # muddiest register -- the minor third E3-G3 is what makes it
            # growl.  Lifting the lower tone an octave leaves the bass
            # carrying an open fifth, which is how C3-G3-E4 already came out
            # well.  Above G3 a third is fine, so the standard G3-B3-D4 shape
            # is left alone.
            if bp < m('G', 3) and min(tp, fp) - bp < 7:
                if tp < fp: tp += 12
                else: fp += 12
            mid.append((b*1.0, 1.0, tp))
            top.append((b*1.0, 1.0, fp))
    return [sorted(bass), sorted(mid), sorted(top)]

def is_chordal(track, thresh=1.15):
    """One line per track gives notes/onset == 1.0; a chordal keyboard track is
    well above that.  Occasional voice overlap must NOT count as chordal, which
    is why this measures simultaneous attacks rather than overlap."""
    onsets = len({s for s, _, _ in track})
    return onsets and len(track)/onsets > thresh

def split_polyphonic(notes, nvoices):
    """Rank each note against everything SOUNDING at its onset, not against the
    other onsets.  An alto note entering over a held bass is then still the alto."""
    out = [[] for _ in range(nvoices)]
    for s, du, a in sorted(notes):
        live = sorted({p for s2, d2, p in notes if s2 - 1e-9 <= s < s2 + qd(d2) - 1e-6}
                      | {a})
        rank = min(live.index(a), nvoices - 1)
        out[rank].append((s, du, a))
    return [sorted(v) for v in out if v]

def derive_voices(tracks, melody_track, nvoices=4):
    mel_tr = tracks[melody_track]
    rest = [t for i, t in enumerate(tracks) if i != melody_track]
    poly = [t for t in rest if is_chordal(t)]
    if rest and not poly:
        rest.sort(key=lambda t: sum(p for _, _, p in t)/len(t))     # lowest first
        return mel_tr, rest, 'one voice per track'
    pool = [n for t in rest for n in t]
    inner = [n for n in mel_tr if n not in set(pool)]
    # non-top notes of the melody track are accompaniment too
    extra = []
    for s, du, a in mel_tr:
        if a != max(snd(mel_tr, s)):
            extra.append((s, du, a))
    voices = split_polyphonic(pool + extra, nvoices)
    return mel_tr, voices, 'split %d polyphonic track(s)' % len(poly)

# -------------------------------------------------------------------- arrange
def arrange(mel_tr, voices, bars, spb=8, melody_both_hands=False):
    """Voices: [bass, tenor, alto, ...] lowest first."""
    NS = bars*spb
    mel = [None]*NS; melsound = [None]*NS; prev = None
    for i in range(NS):
        t = i*0.5; s = snd(mel_tr, t); top = max(s) if s else None
        melsound[i] = top
        if top is not None and (top != prev or top in ons(mel_tr, t)):
            mel[i] = top
        prev = top
    def vsound(vi, t):
        s = snd(voices[vi], t) if vi < len(voices) else []
        return max(s) if s else None

    bassev = [None]*NS; restrike = set()
    if voices:
        for s, du, a in voices[0]:
            i = int(round(s*2))
            if i < NS: bassev[i] = a
        for i in range(NS):                       # keep a held bass speaking
            if bassev[i] is None and i % 2 == 0:
                p = vsound(0, i*0.5)
                if p is not None: bassev[i] = p; restrike.add(i)
    tv = [[] for _ in range(NS)]
    for vi in range(len(voices)-1, 0, -1):        # tenor before alto
        w = WEIGHTS[min(vi, len(WEIGHTS)-1)]
        for s, du, a in voices[vi]:
            i = int(round(s*2))
            if i < NS: tv[i].append((vi, w, a))
    def lowbass(a, dr):
        b = bf(LB, LOWORD, a-12, dr); return (b, a-12) if b else (None, None)

    def slotcost(i, dr, strict=True):
        c = 0; p = melsound[i]
        if p is not None:
            if bf(RB, OR, p, dr): pass
            elif melody_both_hands and bf(LB, OL, p, dr): c += 6   # dip into the left hand
            elif bf(RB, OR, p+12, dr) or bf(RB, OR, p-12, dr): c += 40
            elif strict: return 10**6      # normally reject the direction outright
            else: c += 400                 # ...unless that would dead-end the search
        a = bassev[i]
        if a is not None:
            orig = i not in restrike
            if lowbass(a, dr)[0]: pass
            elif bf(LB, OL, a, dr): c += (9 if orig else 1)
            else: c += (22 if orig else 0)
        ceil = p if p is not None else 200
        for vi, w, x in tv[i]:
            if x <= ceil and (bf(LB, OL, x, dr) or bf(RB, OR, x, dr)): pass
            elif bf(LB, OL, x-12, dr) or bf(LB, OL, x+12, dr): c += w*0.35
            else: c += w*1.0
        return c

    INF = 10**9; best = {(PUSH,0):0, (PULL,0):0}; bk = []
    unplayable = []
    for i in range(NS):
        tie = melsound[i] is not None and mel[i] is None
        for strict in (True, False):           # relax only if nothing survives
            nb = {}; b = {}
            for (dr, run), v in best.items():
                for nd in (PUSH, PULL):
                    sc = slotcost(i, nd, strict)
                    if sc >= 10**6: continue
                    val = v + sc + (0 if nd == dr else (7 if tie else 0))
                    nrun = run+1 if nd == dr else 1
                    val += max(0, nrun-12)*5; key = (nd, min(nrun, 30))
                    if val < nb.get(key, INF): nb[key] = val; b[key] = (dr, run)
            if nb: break
            unplayable.append(i)
        bk.append(b); best = nb
    k = min(best, key=lambda x: best[x]); dirs = [PUSH]*NS
    for i in range(NS-1, -1, -1):
        dirs[i] = k[0]; k = bk[i][k]

    for i in range(1, NS):                        # bass cut by a bellows change
        if bassev[i] is None and dirs[i] != dirs[i-1]:
            p = vsound(0, i*0.5)
            if p is not None: bassev[i] = p; restrike.add(i)
    inner_re = [[] for _ in range(NS)]            # inner voices cut likewise
    for i in range(1, NS):
        if dirs[i] == dirs[i-1]: continue
        for vi in range(len(voices)-1, 0, -1):
            p = vsound(vi, i*0.5)
            if p is None: continue
            if any(x == p for _, _, x in tv[i]): continue
            inner_re[i].append((vi, WEIGHTS[min(vi, len(WEIGHTS)-1)], p))

    changed = []; grid = []; stats = Counter()
    for bar in range(bars):
        row = []
        for e in range(spb):
            i = bar*spb + e; dr = dirs[i]
            cell = {'d': dr, 'R': [], 'L': [], 're': False, 'M': None, 'Mh': 'R'}
            usedL = set(); usedR = set(); picked = []; havep = set()
            show = mel[i] is not None or (melsound[i] is not None and i > 0 and dirs[i-1] != dr)
            if show and melsound[i] is not None:
                p0 = melsound[i]; got = p0; hand = 'R'
                b2 = bf(RB, OR, p0, dr)
                if b2 is None and melody_both_hands:  # try the other hand at pitch
                    b2 = bf(LB, OL, p0, dr)
                    if b2: hand = 'L'; stats['melody notes in left hand'] += 1
                if b2 is None:                        # last resort: an octave away
                    for alt in (p0-12, p0+12):
                        b2 = bf(RB, OR, alt, dr)
                        if b2: got = alt; break
                if b2 is None:
                    changed.append((bar+1, 1+e/2, 'MELODY', nm(p0), 'unplayable'))
                else:
                    if got != p0:
                        changed.append((bar+1, 1+e/2, 'MELODY', nm(p0), nm(got)))
                    cell['M'] = b2; cell['Mh'] = hand; havep.add(got)
                    if hand == 'R': cell['R'].append(b2); usedR.add(b2)
                    else: picked.append((got, b2)); usedL.add(b2)
                    if mel[i] is None: cell['re'] = True; stats['rearticulations'] += 1
            CEIL = melsound[i] if melsound[i] is not None else 200
            def muddy(p): return any(0 < abs(p-q) <= 2 and min(p, q) < m('G',4) for q in havep)

            a = bassev[i]
            if a is not None and i not in restrike:
                lo, lp = lowbass(a, dr)
                if lo:
                    picked.append((lp, lo)); usedL.add(lo); havep.add(lp); stats['bass low octave'] += 1
                else:
                    b2 = bf(LB, OL, a, dr)
                    if b2:
                        picked.append((a, b2)); usedL.add(b2); havep.add(a)
                    else:
                        pcs = set(x % 12 for _, _, x in tv[i])
                        for vi2 in range(1, len(voices)):
                            p3 = vsound(vi2, i*0.5)
                            if p3 is not None: pcs.add(p3 % 12)
                        if melsound[i] is not None: pcs.add(melsound[i] % 12)
                        cand = [(abs(LB[x][dr]-a+12), LB[x][dr], x) for x in LOWORD
                                if x not in usedL and LB[x][dr] % 12 in pcs
                                and LB[x][dr] <= m('A',4)]
                        if cand:
                            _, p2, x = min(cand)
                            picked.append((p2, x)); usedL.add(x); havep.add(p2)
                            changed.append((bar+1, 1+e/2, 'bass', nm(a), nm(p2)))
                        else:
                            changed.append((bar+1, 1+e/2, 'bass', nm(a), 'omitted'))
            for vi, w, x in sorted(tv[i], key=lambda y: -y[1]):
                cands = []
                b2 = bf(LB, OL, x, dr)
                if b2 and b2 not in usedL and len(picked) < 3: cands.append((0, x, 'L', b2))
                b2 = bf(RB, OR, x, dr)
                if b2 and b2 not in usedR and len(cell['R']) < 3: cands.append((1, x, 'R', b2))
                b2 = bf(LB, OL, x-12, dr)
                if b2 and b2 not in usedL and len(picked) < 3: cands.append((4, x-12, 'L', b2))
                b2 = bf(LB, OL, x+12, dr)
                if b2 and b2 not in usedL and len(picked) < 3: cands.append((7, x+12, 'L', b2))
                if vi == 1:                       # the tenor may take a chord tone
                    pcs = set(y % 12 for _, _, y in tv[i]) | ({bassev[i] % 12} if bassev[i] else set())
                    for z in OL:
                        p2 = LB[z][dr]
                        if p2 % 12 in pcs and abs(p2-x) <= 7 and z not in usedL and len(picked) < 3:
                            cands.append((8, p2, 'L', z))
                cands = [(pen + (9 if muddy(p2) else 0), p2, h, b3) for pen, p2, h, b3 in cands
                         if p2 not in havep and p2 <= CEIL]
                if not cands:
                    changed.append((bar+1, 1+e/2, 'voice %d' % vi, nm(x), 'omitted')); continue
                pen, p2, h, b3 = min(cands)
                if p2 != x:
                    changed.append((bar+1, 1+e/2, 'voice %d' % vi, nm(x), nm(p2)))
                havep.add(p2)
                if h == 'L': usedL.add(b3); picked.append((p2, b3))
                else: usedR.add(b3); cell['R'].append(b3); stats['inner notes in right hand'] += 1
            for vi, w, x in sorted(inner_re[i], key=lambda y: -y[1]):
                cands = []
                b2 = bf(LB, OL, x, dr)
                if b2 and b2 not in usedL and len(picked) < 3: cands.append((0, x, 'L', b2))
                b2 = bf(RB, OR, x, dr)
                if b2 and b2 not in usedR and len(cell['R']) < 3: cands.append((1, x, 'R', b2))
                b2 = bf(LB, OL, x-12, dr)
                if b2 and b2 not in usedL and len(picked) < 3: cands.append((4, x-12, 'L', b2))
                cands = [c for c in cands if c[1] not in havep and not muddy(c[1]) and c[1] <= CEIL]
                if not cands: continue
                pen, p2, h, b3 = min(cands); havep.add(p2); stats['inner re-strikes'] += 1
                if h == 'L': usedL.add(b3); picked.append((p2, b3))
                else: usedR.add(b3); cell['R'].append(b3)
            rb = bassev[i] if i in restrike else None
            if rb is not None and len(picked) < 3:
                lo, lp = lowbass(rb, dr); opts = ([(lp, lo)] if lo else [])
                b3 = bf(LB, OL, rb, dr)
                if b3: opts.append((rb, b3))
                for p2, b3 in opts:
                    if b3 in usedL or p2 in havep: continue
                    if any(0 < abs(p2-q) <= 2 for q, _ in picked): continue
                    picked.append((p2, b3)); usedL.add(b3); havep.add(p2)
                    stats['bass re-strikes'] += 1; break
            seen = set(); uniq = []                     # never sound one pitch twice
            for p2, b3 in sorted(picked):
                if p2 in seen: continue
                seen.add(p2); uniq.append((p2, b3))
            cell['L'] = [x for _, x in uniq]
            cell['R'] = sorted(cell['R'], key=lambda b: RB[b][dr])
            row.append(cell)
        grid.append(row)
    return grid, mel, melsound, changed, stats

# ---------------------------------------------------------------- verification
def verify(grid, mel, melsound, voices, mel_tr, bars, changed=(), spb=8):
    NS = bars*spb; ok = True
    def heard(c):
        return ([RB[x][c['d']] for x in c['R']] + [LB[x][c['d']] for x in c['L']])
    bad = sum(1 for b in range(bars) for e in range(spb)
              if mel[b*spb+e] is not None and mel[b*spb+e] not in heard(grid[b][e]))
    print('melody mismatches: %d%s' % (bad, '' if bad == 0 else '   <-- MUST be 0'))
    ok &= bad == 0

    # what actually sounds: a note lasts until the bellows turns or its button repeats
    live = {}; prevd = None; missing = []
    for b in range(bars):
        for e in range(spb):
            i = b*spb+e; c = grid[b][e]; d = c['d']
            if d != prevd: live = {}
            prevd = d
            for x in c['R']: live[('R', x)] = RB[x][d]
            for x in c['L']: live[('L', x)] = LB[x][d]
            want = set(snd(mel_tr, i*0.5))
            for v in voices: want |= set(snd(v, i*0.5))
            gap = {p % 12 for p in want} - {p % 12 for p in set(live.values())}
            if gap: missing.append((b+1, 1+e/2, sorted(NM[g] for g in gap)))
    print('slots missing a pitch class: %d of %d' % (len(missing), NS))
    for row in missing[:10]:
        print('    bar %-3d beat %-4g  %s' % row)
    def pclass(name): return name.rstrip('-0123456789')
    oct_moved = [r for r in changed if r[2].startswith('voice')
                 and r[4] != 'omitted' and pclass(r[3]) == pclass(r[4])]
    print('inner-voice notes moved to another octave: %d%s'
          % (len(oct_moved), '' if not oct_moved else '   <-- breaks stepwise inner lines'))
    for r in oct_moved[:6]:
        print('    bar %-3d beat %-4g %s -> %s' % (r[0], r[1], r[3], r[4]))
    above = [(b+1, 1+e/2) for b in range(bars) for e in range(spb)
             for x in grid[b][e]['L']
             if melsound[b*spb+e] and LB[x][grid[b][e]['d']] > melsound[b*spb+e]
             and not (grid[b][e]['Mh'] == 'L' and x == grid[b][e]['M'])]
    print('accompaniment above the melody: %d%s' % (len(above), '' if not above else '   <-- should be 0'))
    ok &= not above
    runs = []; cur = None; n = 0
    for b in grid:
        for c in b:
            if c['d'] == cur: n += 1
            else:
                if cur is not None: runs.append(n)
                cur = c['d']; n = 1
    runs.append(n)
    print('bellows runs (eighths): %s' % sorted(Counter(runs).items()))
    if max(runs) > 12:
        print('    <-- a run past 12 eighths is unplayable'); ok = False
    used = Counter(x for b in grid for c in b for x in c['L'])
    print('left-hand buttons used: %s' % ' '.join('%s:%d' % kv for kv in
                                                  sorted(used.items(), key=lambda kv: -kv[1])))
    if not {'1', '1a', '2', '6', '2a'} & set(used):
        print('    <-- no low left-hand buttons: the voicing has collapsed into one octave')
        ok = False
    return ok

# -------------------------------------------------------------------- engrave
def engrave(grid, bars, path, title, subtitle, per_line=4, sections=None, spb=8):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import HexColor
    W, H = A4
    INK, RULE = HexColor('#1c2528'), HexColor('#2f4a3f')
    ACC, SOFT, CELL = HexColor('#4a6f86'), HexColor('#6b7679'), HexColor('#c5ccc6')
    Mg, GUT = 26, 15
    X0, XE = Mg+GUT, W-Mg
    SLOT = (XE-X0) / (per_line*spb)
    RH, LHH, PITCH = 39, 38, 85
    FM, FA, LSP = 11.8, 9.4, 10.4
    c = canvas.Canvas(path, pagesize=A4); c.setTitle(title)

    def num(xc, yb, lab, size, col, pull):
        w = c.stringWidth(lab, 'Helvetica', size); x = xc - w/2
        c.setFillColor(col); c.setFont('Helvetica', size); c.drawString(x, yb, lab)
        if pull:
            c.setStrokeColor(col); c.setLineWidth(0.95)
            c.line(x-0.7, yb+size*0.80, x+w+0.7, yb+size*0.80)

    def system(ytop, bar0, final):
        ymid, ybot = ytop-RH, ytop-RH-LHH
        c.setFillColor(SOFT); c.setFont('Helvetica', 7.5)
        c.drawRightString(X0-5, ytop-11, str(bar0+1))
        for k in range(per_line):
            x0 = X0 + k*spb*SLOT
            c.setStrokeColor(CELL); c.setLineWidth(0.5); c.setDash([2, 2])
            for beat in range(1, spb//2):                 # one guide per beat
                c.line(x0+2*beat*SLOT, ytop, x0+2*beat*SLOT, ybot)
            c.setDash()
            if bar0+k >= bars: continue
            for e in range(spb):
                cell = grid[bar0+k][e]; pull = cell['d'] == PULL
                xc = x0 + (e+0.5)*SLOT
                top = ymid + 8 + 2*LSP                      # melody on a fixed line
                onR = cell['M'] if cell['Mh'] == 'R' else None
                if onR: num(xc, top, onR, FM, INK, pull)
                rest = sorted([b for b in cell['R'] if b != onR],
                              key=lambda b: RB[b][cell['d']], reverse=True)
                for n2, b in enumerate(rest):
                    num(xc, top-(n2+1)*LSP, b, FA, ACC, pull)
                for n2, b in enumerate(sorted(cell['L'], key=lambda b: LB[b][cell['d']],
                                              reverse=True)):
                    isMel = cell['Mh'] == 'L' and b == cell['M']
                    num(xc, ymid-13-n2*LSP, b, FM if isMel else FA,
                        INK if isMel else ACC, pull)
        c.setStrokeColor(CELL); c.setLineWidth(0.6); c.line(X0, ymid, XE, ymid)
        c.setStrokeColor(RULE); c.setLineWidth(1.1)
        c.line(X0, ytop, XE, ytop); c.line(X0, ybot, XE, ybot)
        for k in range(per_line+1):                         # close BOTH ends
            c.line(X0+k*spb*SLOT, ytop, X0+k*spb*SLOT, ybot)
        if final:
            c.line(XE-4, ytop, XE-4, ybot)
            c.setLineWidth(2.6); c.line(XE-1.3, ytop, XE-1.3, ybot)

    c.setFillColor(INK); c.setFont('Helvetica-Bold', 15); c.drawString(Mg, H-42, title)
    c.setFillColor(SOFT); c.setFont('Helvetica', 8.3)
    words, line, lines = subtitle.split(), '', []        # wrap rather than run off the page
    for w in words:
        trial = (line + ' ' + w).strip()
        if c.stringWidth(trial, 'Helvetica', 8.3) > XE - Mg:
            lines.append(line); line = w
        else:
            line = trial
    lines.append(line)
    for n2, ln in enumerate(lines[:3]):
        c.drawString(Mg, H-54-n2*10, ln)
    y = H-72 - max(0, len(lines[:3])-1)*10
    sections = sections or [('', 0)]
    for name, b0 in sections:
        if name:
            c.setFillColor(RULE); c.setFont('Helvetica-Bold', 10)
            c.drawString(Mg, y-9, name); y -= 16
        end = next((s[1] for s in sections if s[1] > b0), bars)
        for k in range(b0, end, per_line):
            if y < 90: c.showPage(); y = H-60
            system(y, k, k+per_line >= end); y -= PITCH
        y -= 4
    c.save()

# ------------------------------------------------------------------------ cli
def parse_chords(text, bars, beats):
    """'Am | E | Am | Dm' -- one symbol per bar, '|' or ',' separated, '%' or
    '-' repeats the previous bar.  Two symbols in a bar split it at the last
    beat.  Returns one chord per beat, so it drops straight into the arranger."""
    names = {'C':0,'C#':1,'DB':1,'D':2,'D#':3,'EB':3,'E':4,'F':5,'F#':6,'GB':6,
             'G':7,'G#':8,'AB':8,'A':9,'A#':10,'BB':10,'B':11}
    def one(sym):
        sym = sym.strip()
        if not sym or sym in ('%', '-'): return None
        qual = 'm' if sym[1:].lower().startswith('m') and not sym[1:].lower().startswith('maj') else ''
        for n in sorted(names, key=len, reverse=True):
            if sym.upper().startswith(n):
                return (names[n], 'm' if sym[len(n):].lower().startswith('m')
                        and not sym[len(n):].lower().startswith('maj') else '')
        raise SystemExit('cannot read chord %r' % sym)
    out, prev = [], None
    cells = [c for c in text.replace(',', '|').split('|')]
    for b in range(bars):
        cell = cells[b] if b < len(cells) else ''
        parts = [p for p in cell.split() if p]
        if not parts:
            out += [prev]*beats; continue
        if len(parts) == 1:
            ch = one(parts[0]) or prev
            out += [ch]*beats; prev = ch
        else:
            a2, b2 = one(parts[0]) or prev, one(parts[1]) or prev
            out += [a2]*(beats-1) + [b2]; prev = b2
    return out

def build(midi, bars=0, melody_track=0, beats=0, transpose=0, melody_both_hands=False,
          grid=0, fakebook=False, chord_text=''):
    tracks, ts = read_midi(midi)
    if transpose:
        tracks = [[(s, d, p+transpose) for s, d, p in tr] for tr in tracks]
    if grid:
        tracks = quantize(tracks, grid)
    beats = beats or ts
    spb = beats*2
    mel_tr, voices, how = derive_voices(tracks, melody_track)
    span = max(s+qd(d) for tr in tracks for s, d, _ in tr)
    bars = bars or int(round(span/beats))
    chords = None
    if fakebook:
        chords = (parse_chords(chord_text, bars, beats) if chord_text
                  else detect_chords(tracks, voices, bars, beats))
        # Bars the source leaves unaccompanied are an intro figure, not a tune
        # over chords.  Flattening those to melody-plus-oompah loses the figure
        # entirely, so keep the melody track exactly as written there.
        #
        # A lead-in counts too.  Testing only "has any accompaniment at all"
        # missed a pickup bar whose bass walks in halfway through: the bar got
        # a full oompah stamped over a figure that has not started yet.  So
        # also pass over the bars before the first one the accompaniment
        # attacks in its own first half.  That leading-bars-only test is what
        # keeps a mid-piece bar of sustained harmony from being mistaken for
        # an intro.
        acc_tracks = [t for i, t in enumerate(tracks) if i != melody_track]
        played = {int(s2//beats) for t in acc_tracks for s2, d2, p2 in t}
        onbeat = sorted(int(s2//beats) for t in acc_tracks for s2, d2, p2 in t
                        if s2 % beats < beats*0.5)
        solo = (set(range(bars)) - played) | set(range(onbeat[0] if onbeat else 0))
        kept = []
        for s2, d2, p2 in mel_tr:
            if int(s2//beats) in solo:
                top = max(snd(mel_tr, s2) or [p2])
                if p2 != top: kept.append((s2, d2, p2))
        voices = fakebook_voices(chords, bars, beats, solo) + ([sorted(kept)] if kept else [])
        how = ('fakebook: melody + chords (%d intro bar(s) kept as written)' % len(solo)
               if solo else 'fakebook: melody + chords')
    g, mel, melsound, changed, stats = arrange(mel_tr, voices, bars, spb, melody_both_hands)
    return g, mel, melsound, changed, stats, voices, mel_tr, bars, how, spb, chords

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('midi'); ap.add_argument('-o', '--out', default='tab.pdf')
    ap.add_argument('--title', default='Untitled'); ap.add_argument('--subtitle', default='')
    ap.add_argument('--bars', type=int, default=0)
    ap.add_argument('--per-line', type=int, default=4)
    ap.add_argument('--melody-track', type=int, default=0)
    ap.add_argument('--beats', type=int, default=0, help='beats per bar (default: from the MIDI)')
    ap.add_argument('--transpose', type=int, default=0, help='semitones, applied to every track')
    ap.add_argument('--chords', default='',
                    help='chord chart, one symbol per bar: "Am | E | Am | Dm | %% | G7"')
    ap.add_argument('--fakebook', action='store_true',
                    help='melody plus a plain chord accompaniment, ignoring the piano texture')
    ap.add_argument('--straight', action='store_true',
                    help='snap onsets to the eighth grid: rolled chords and ornaments play on the beat')
    ap.add_argument('--melody-both-hands', action='store_true',
                    help='let the melody dip into the left hand when the right cannot reach it')
    ap.add_argument('--sections', default='', help='e.g. "A1:0,A2:8,B1:16"')
    ap.add_argument('--dump-grid', default='', help='write the arrangement as JSON')
    a = ap.parse_args()
    grid, mel, msound, changed, stats, voices, mel_tr, bars, how, spb, chords = \
        build(a.midi, a.bars, a.melody_track, a.beats, a.transpose, a.melody_both_hands,
              0.5 if a.straight else 0, a.fakebook, a.chords)
    if chords:
        syms = []
        for b in range(bars):
            c = chords[b*(spb//2)]
            syms.append(('%s%s' % (NM[c[0]], c[1])) if c else '-')
        print('--- chord chart')
        for i in range(0, bars, 9):
            print('    bars %3d-%-3d | %s' % (i+1, min(i+9, bars),
                  ' | '.join('%-4s' % x for x in syms[i:i+9])))
    print('--- %d/4 time, %d bars; voices: %s, %d accompaniment voice(s)'
          % (spb//2, bars, how, len(voices)))
    print('--- verification')
    verify(grid, mel, msound, voices, mel_tr, bars, changed, spb)
    for k in sorted(stats): print('%s: %d' % (k, stats[k]))
    print('--- notes changed from the source: %d' % len(changed))
    for row in changed:
        print('    bar %-3d beat %-4g %-8s %s -> %s' % row)
    if a.dump_grid:
        json.dump(grid, open(a.dump_grid, 'w'))
    secs = [(s.split(':')[0], int(s.split(':')[1])) for s in a.sections.split(',')] if a.sections else None
    sub = a.subtitle or ('Jeffries anglo. Right hand above, left hand below; melody in black, '
                         'accompaniment in blue. A line over a number means pull.')
    engrave(grid, bars, a.out, a.title, sub, a.per_line, secs, spb)
    print('--- wrote %s' % a.out)
