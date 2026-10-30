#!/usr/bin/env python3
"""Arrange a MIDI file for 30-button C/G Jeffries anglo concertina and engrave
button tablature as a PDF.

  python3 anglotab.py tune.mid -o tune.pdf --title "Tune name"

Track 0 carries the melody (its top line); everything else, including non-top
notes of that track, becomes the accompaniment pool, so it works on both
part-per-track consort scores and polyphonic keyboard tracks.  Prints a
verification report -- read it before trusting the output.
"""
import argparse, struct, sys
from collections import Counter

# ---------------------------------------------------------------- note tables
def M(n, o):
    return {'C':0,'C#':1,'D':2,'D#':3,'E':4,'F':5,'F#':6,
            'G':7,'G#':8,'A':9,'A#':10,'B':11}[n] + 12*(o+1)
NAMES = ['C','C#','D','Eb','E','F','F#','G','Ab','A','Bb','B']
def nm(p): return NAMES[p % 12] + str(p//12 - 1)

# (push, pull).  Row numbering: 1a-5a accidentals, 1-5 C row, 6-10 G row.
LEFT = {'1':(M('C',3),M('G',3)),  '2':(M('G',3),M('B',3)),  '3':(M('C',4),M('D',4)),
        '4':(M('E',4),M('F',4)),  '5':(M('G',4),M('A',4)),  '6':(M('G',3),M('D',4)),
        '7':(M('D',4),M('F#',4)), '8':(M('G',4),M('A',4)),  '9':(M('B',4),M('C',5)),
        '10':(M('D',5),M('E',5)), '1a':(M('E',3),M('F',3)), '2a':(M('A',3),M('A#',3)),
        '3a':(M('C#',4),M('D#',4)),'4a':(M('A',4),M('G',4)),'5a':(M('G#',4),M('A#',4))}
RIGHT = {'1':(M('C',5),M('B',4)), '2':(M('E',5),M('D',5)), '3':(M('G',5),M('F',5)),
         '4':(M('C',6),M('A',5)), '5':(M('E',6),M('B',5)), '6':(M('G',5),M('F#',5)),
         '7':(M('B',5),M('A',5)), '8':(M('D',6),M('C',6)), '9':(M('G',6),M('E',6)),
         '10':(M('B',6),M('F#',6)),'1a':(M('D#',5),M('C#',5)),'2a':(M('C#',5),M('D#',5)),
         '3a':(M('G#',5),M('G',5)),'4a':(M('C#',6),M('A#',5)),'5a':(M('A',5),M('D',6))}
# search order: C row first, then G row, then accidentals
ORD_L = ['3','4','5','7','9','1','2','8','10','6','1a','4a','2a','5a','3a']
ORD_R = ['1','2','3','4','5','6','7','8','5a','3a','1a','2a','9','10','4a']
LOW_L = ['1','1a','2','6','2a','3','7','4','5','8','9','10','4a','5a','3a']
PUSH, PULL = 0, 1

def find(table, order, pitch, d, exclude=()):
    for b in order:
        if table[b][d] == pitch and b not in exclude:
            return b
    return None

# -------------------------------------------------------------- midi parsing
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
    p, tracks = 14, []
    for _ in range(ntr):
        ln = struct.unpack('>I', data[p+4:p+8])[0]
        buf = data[p+8:p+8+ln]; p += 8 + ln
        i = tick = 0; status = None; on = {}; notes = []
        while i < len(buf):
            dt, i = vlq(buf, i); tick += dt; st = buf[i]
            if st == 0xff:
                n, j = vlq(buf, i+2); i = j + n; continue
            if st in (0xf0, 0xf7):
                n, j = vlq(buf, i+1); i = j + n; continue
            if st & 0x80:
                status = st; i += 1
            ev = status & 0xf0
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
    return tracks

def qdur(d):
    """Sequencers write ~95% of nominal length; snap back to the grid.  Without
    this, releases overlap the next downbeat and every melody note lands late."""
    return max(0.5, round(d / 0.95 * 4) / 4)

def sounding(track, t):
    return [p for s, d, p in track if s - 1e-9 <= t < s + qdur(d) - 1e-6]
def onsets(track, t):
    return [p for s, d, p in track if abs(s - t) < 1e-6]

# ------------------------------------------------------------------- arrange
def arrange(tracks, bars, melody_track=0):
    NS = bars * 8
    mel_tr = tracks[melody_track]

    # melody = highest SOUNDING pitch, not highest onset
    mel = [None]*NS; msound = [None]*NS; prev = None
    for i in range(NS):
        t = i*0.5; s = sounding(mel_tr, t); top = max(s) if s else None
        msound[i] = top
        if top is not None and (top != prev or top in onsets(mel_tr, t)):
            mel[i] = top
        prev = top

    # Accompaniment pool: every non-melody track, plus any note of the melody
    # track that is not the top line.  This makes the solver work equally on
    # part-per-track consort scores and on polyphonic keyboard tracks.
    pool = [n for i, tr in enumerate(tracks) if i != melody_track for n in tr]
    for s, d, p in mel_tr:
        i = int(round(s*2))
        if not (0 <= i < NS) or mel[i] != p:
            pool.append((s, d, p))
    pool.sort()

    def pool_sounding(t):
        return sorted({p for s, d, p in pool if s - 1e-9 <= t < s + qdur(d) - 1e-6})
    WEIGHT = [20, 16, 11, 8, 6]
    def w_of(rank): return WEIGHT[min(rank, len(WEIGHT)-1)]

    bassev = [None]*NS; restrike = set(); inner = [[] for _ in range(NS)]
    for i in range(NS):
        t = i*0.5
        hits = sorted({p for s, d, p in pool if abs(s-t) < 1e-6})
        if hits:
            bassev[i] = hits[0]
            for r, p in enumerate(hits[1:]):
                inner[i].append((r+1, w_of(r+1), p))
        elif i % 2 == 0:                          # keep a held bass speaking
            snd = pool_sounding(t)
            if snd: bassev[i] = snd[0]; restrike.add(i)

    def low(p, d):
        b = find(LEFT, LOW_L, p-12, d)
        return (b, p-12) if b else (None, None)

    def cost(i, d):
        c = 0; p = msound[i]
        if p is not None:
            if find(RIGHT, ORD_R, p, d): pass
            elif find(RIGHT, ORD_R, p+12, d) or find(RIGHT, ORD_R, p-12, d): c += 40
            else: return 10**6
        a = bassev[i]
        if a is not None:
            orig = i not in restrike
            if low(a, d)[0]: pass
            elif find(LEFT, ORD_L, a, d): c += (9 if orig else 1)
            else: c += (22 if orig else 0)
        ceil = p if p is not None else 200
        for vi, w, x in inner[i]:
            if x <= ceil and (find(LEFT, ORD_L, x, d) or find(RIGHT, ORD_R, x, d)): pass
            elif find(LEFT, ORD_L, x-12, d) or find(LEFT, ORD_L, x+12, d): c += w*0.35
            else: c += w
        return c

    INF = 10**9; best = {(PUSH,0):0, (PULL,0):0}; back = []
    for i in range(NS):
        nxt, bk = {}, {}
        tied = msound[i] is not None and mel[i] is None   # melody sustaining
        for (d, run), v in best.items():
            for nd in (PUSH, PULL):
                c = cost(i, nd)
                if c >= 10**6: continue
                nrun = run+1 if nd == d else 1
                val = v + c + (0 if nd == d else (7 if tied else 0)) + max(0, nrun-12)*5
                key = (nd, min(nrun, 30))
                if val < nxt.get(key, INF): nxt[key] = val; bk[key] = (d, run)
        back.append(bk); best = nxt
    k = min(best, key=lambda x: best[x]); dirs = [PUSH]*NS
    for i in range(NS-1, -1, -1):
        dirs[i] = k[0]; k = back[i][k]

    inner_re = [[] for _ in range(NS)]
    for i in range(1, NS):                      # notes cut off by a bellows change
        if dirs[i] == dirs[i-1]: continue
        snd = pool_sounding(i*0.5)
        if not snd: continue
        if bassev[i] is None:
            bassev[i] = snd[0]; restrike.add(i); snd = snd[1:]
        for r, p in enumerate(snd):
            if not any(x == p for _, _, x in inner[i]):
                inner_re[i].append((r+1, w_of(r+1), p))

    grid = []; notes_changed = []
    for bar in range(bars):
        row = []
        for e in range(8):
            i = bar*8 + e; d = dirs[i]
            cell = {'d': d, 'R': [], 'L': [], 'M': None, 're': False}
            usedL, usedR, held = set(), set(), set()
            ceil = msound[i] if msound[i] is not None else 200
            show = mel[i] is not None or (msound[i] is not None and i > 0 and dirs[i-1] != d)
            if show and msound[i] is not None:
                b = find(RIGHT, ORD_R, msound[i], d)
                cell['R'].append(b); cell['M'] = b; usedR.add(b); held.add(msound[i])
                if mel[i] is None: cell['re'] = True

            def place(vi, w, x, optional):
                """Try, in order: left at pitch, right at pitch, left an octave
                down, left an octave up, chord-tone substitute (not if optional)."""
                cands = []
                b = find(LEFT, ORD_L, x, d)
                if b and b not in usedL and len(cell['L']) < 3: cands.append((0, x, 'L', b))
                b = find(RIGHT, ORD_R, x, d)
                if b and b not in usedR and len(cell['R']) < 3: cands.append((1, x, 'R', b))
                for pen, alt in ((4, x-12), (7, x+12)):
                    b = find(LEFT, ORD_L, alt, d)
                    if b and b not in usedL and len(cell['L']) < 3: cands.append((pen, alt, 'L', b))
                if not optional:
                    pcs = {y % 12 for _, _, y in inner[i]} | ({bassev[i] % 12} if bassev[i] else set())
                    if msound[i]: pcs.add(msound[i] % 12)
                    for z in ORD_L:
                        p2 = LEFT[z][d]
                        if p2 % 12 in pcs and abs(p2-x) <= 7 and z not in usedL and len(cell['L']) < 3:
                            cands.append((8, p2, 'L', z))
                def muddy(p2):
                    return any(0 < abs(p2-q) <= 2 and min(p2, q) < M('G',4) for q in held)
                cands = [c for c in cands if c[1] not in held and c[1] <= ceil and not muddy(c[1])]
                if not cands: return None
                pen, p2, hand, b = min(cands)
                held.add(p2)
                (usedL if hand == 'L' else usedR).add(b)
                (cell['L'] if hand == 'L' else cell['R']).append(b)
                return p2

            a = bassev[i]
            if a is not None and i not in restrike:
                b, p2 = low(a, d)
                if b:
                    cell['L'].append(b); usedL.add(b); held.add(p2)
                else:
                    b = find(LEFT, ORD_L, a, d)
                    if b:
                        cell['L'].append(b); usedL.add(b); held.add(a)
                    else:
                        pcs = {y % 12 for y in pool_sounding(i*0.5)}
                        if msound[i]: pcs.add(msound[i] % 12)
                        c2 = [(abs(LEFT[z][d]-a+12), LEFT[z][d], z) for z in LOW_L
                              if z not in usedL and LEFT[z][d] % 12 in pcs
                              and LEFT[z][d] <= min(M('A',4), ceil)]
                        if c2:
                            _, p2, z = min(c2)
                            cell['L'].append(z); usedL.add(z); held.add(p2)
                            notes_changed.append((bar+1, 1+e/2, 'bass', nm(a), nm(p2)))
                        else:
                            notes_changed.append((bar+1, 1+e/2, 'bass', nm(a), 'omitted'))
            for vi, w, x in sorted(inner[i], key=lambda y: -y[1]):
                got = place(vi, w, x, optional=False)
                if got is None:
                    notes_changed.append((bar+1, 1+e/2, 'voice %d' % vi, nm(x), 'omitted'))
                elif got != x:
                    notes_changed.append((bar+1, 1+e/2, 'voice %d' % vi, nm(x), nm(got)))
            for vi, w, x in sorted(inner_re[i], key=lambda y: -y[1]):
                place(vi, w, x, optional=True)
            rb = bassev[i] if i in restrike else None
            if rb is not None and len(cell['L']) < 3:
                b, p2 = low(rb, d)
                for cand, pitch in ([(b, p2)] if b else []) + [(find(LEFT, ORD_L, rb, d), rb)]:
                    if cand and cand not in usedL and pitch not in held and pitch <= ceil \
                       and not any(0 < abs(pitch-q) <= 2 for q in held):
                        cell['L'].append(cand); held.add(pitch); break
            cell['L'].sort(key=lambda b: LEFT[b][d])
            cell['R'].sort(key=lambda b: RIGHT[b][d])
            row.append(cell)
        grid.append(row)
    return grid, mel, msound, notes_changed

# ---------------------------------------------------------------- verification
def verify(grid, tracks, mel, msound, bars):
    NS = bars*8; ok = True
    bad = sum(1 for b in range(bars) for e in range(8)
              if mel[b*8+e] is not None
              and mel[b*8+e] not in [RIGHT[x][grid[b][e]['d']] for x in grid[b][e]['R']])
    print('melody mismatches: %d%s' % (bad, '' if bad == 0 else '   <-- MUST be 0'))
    ok &= bad == 0
    live = {}; prev = None; missing = []
    for b in range(bars):
        for e in range(8):
            i = b*8+e; c = grid[b][e]; d = c['d']
            if d != prev: live = {}
            prev = d
            for x in c['R']: live[('R', x)] = RIGHT[x][d]
            for x in c['L']: live[('L', x)] = LEFT[x][d]
            want = set()
            for tr in tracks:
                want |= set(sounding(tr, i*0.5))
            gap = {p % 12 for p in want} - {p % 12 for p in live.values()}
            if gap: missing.append((b+1, 1+e/2, sorted(NAMES[g] for g in gap)))
    print('slots missing a pitch class: %d of %d' % (len(missing), NS))
    for mrow in missing[:12]:
        print('    bar %-3d beat %-4g  %s' % mrow)
    above = [(b+1, 1+e/2) for b in range(bars) for e in range(8)
             for x in grid[b][e]['L']
             if msound[b*8+e] and LEFT[x][grid[b][e]['d']] > msound[b*8+e]]
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
    if max(runs) > 12: print('    <-- a run past 12 eighths is unplayable'); ok = False
    used = Counter(x for b in grid for c in b for x in c['L'])
    print('left-hand buttons used: %s' % ' '.join('%s:%d' % kv for kv in sorted(used.items(), key=lambda kv: -kv[1])))
    if not {'1', '1a', '2', '6', '2a'} & set(used):
        print('    <-- no low left-hand buttons: the voicing is probably collapsed')
    return ok

# -------------------------------------------------------------------- engrave
def engrave(grid, bars, path, title, subtitle, per_line=4, sections=None):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import HexColor
    W, H = A4
    INK, RULE = HexColor('#1c2528'), HexColor('#2f4a3f')
    ACC, SOFT, CELL = HexColor('#4a6f86'), HexColor('#6b7679'), HexColor('#c5ccc6')
    Mg, GUT = 26, 15
    X0, XE = Mg+GUT, W-Mg
    SLOT = (XE-X0) / (per_line*8)
    RH, LHH, PITCH = 39, 38, 85
    FM, FA, LSP = 11.8, 9.4, 10.4
    c = canvas.Canvas(path, pagesize=A4)
    c.setTitle(title)

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
            x0 = X0 + k*8*SLOT
            c.setStrokeColor(CELL); c.setLineWidth(0.5); c.setDash([2, 2])
            c.line(x0+4*SLOT, ytop, x0+4*SLOT, ybot); c.setDash()
            for e in range(8):
                if bar0+k >= bars: break
                cell = grid[bar0+k][e]; pull = cell['d'] == PULL
                xc = x0 + (e+0.5)*SLOT
                top = ymid + 8 + 2*LSP                     # melody on a fixed line
                if cell['M']: num(xc, top, cell['M'], FM, INK, pull)
                rest = sorted([b for b in cell['R'] if b != cell['M']],
                              key=lambda b: RIGHT[b][cell['d']], reverse=True)
                for n2, b in enumerate(rest):
                    num(xc, top-(n2+1)*LSP, b, FA, ACC, pull)
                for n2, b in enumerate(sorted(cell['L'], key=lambda b: LEFT[b][cell['d']],
                                              reverse=True)):
                    num(xc, ymid-13-n2*LSP, b, FA, ACC, pull)   # highest under the divider
        c.setStrokeColor(CELL); c.setLineWidth(0.6); c.line(X0, ymid, XE, ymid)
        c.setStrokeColor(RULE); c.setLineWidth(1.1)
        c.line(X0, ytop, XE, ytop); c.line(X0, ybot, XE, ybot)
        for k in range(per_line+1):                        # close BOTH ends
            c.line(X0+k*8*SLOT, ytop, X0+k*8*SLOT, ybot)
        if final:
            c.line(XE-4, ytop, XE-4, ybot)
            c.setLineWidth(2.6); c.line(XE-1.3, ytop, XE-1.3, ybot)

    c.setFillColor(INK); c.setFont('Helvetica-Bold', 15); c.drawString(Mg, H-42, title)
    c.setFillColor(SOFT); c.setFont('Helvetica', 8.3); c.drawString(Mg, H-54, subtitle)
    y = H-72
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
if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('midi'); ap.add_argument('-o', '--out', default='tab.pdf')
    ap.add_argument('--title', default='Untitled'); ap.add_argument('--subtitle', default='')
    ap.add_argument('--bars', type=int, default=0, help='bars to arrange (default: all)')
    ap.add_argument('--per-line', type=int, default=4)
    ap.add_argument('--melody-track', type=int, default=0)
    ap.add_argument('--sections', default='', help='e.g. "A1:0,A2:8,B1:16"')
    a = ap.parse_args()
    tracks = read_midi(a.midi)
    span = max(s+qdur(d) for tr in tracks for s, d, _ in tr)
    bars = a.bars or int(round(span/4))
    grid, mel, msound, changed = arrange(tracks, bars, a.melody_track)
    print('--- verification')
    verify(grid, tracks, mel, msound, bars)
    print('--- notes changed from the source: %d' % len(changed))
    for row in changed:
        print('    bar %-3d beat %-4g %-8s %s -> %s' % row)
    secs = [(s.split(':')[0], int(s.split(':')[1])) for s in a.sections.split(',')] if a.sections else None
    sub = a.subtitle or 'Jeffries anglo. Right hand above, left hand below; melody in black, accompaniment in blue. A line over a number means pull.'
    engrave(grid, bars, a.out, a.title, sub, a.per_line, secs)
    print('--- wrote %s' % a.out)
