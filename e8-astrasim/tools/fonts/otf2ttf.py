# OTF (CFF) -> TTF (glyf) for matplotlib's Type 42 PDF embedding (fontTools snippet otf2ttf.py, cu2qu)
import sys
from fontTools.ttLib import TTFont, newTable
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
for src in sys.argv[1:]:
    f = TTFont(src)
    gs = f.getGlyphSet(); order = f.getGlyphOrder(); glyf = {}
    for n in order:
        p = TTGlyphPen(gs); gs[n].draw(Cu2QuPen(p, 1.0, reverse_direction=True)); glyf[n] = p.glyph()
    f['loca'] = newTable('loca'); f['glyf'] = t = newTable('glyf'); t.glyphOrder = order; t.glyphs = glyf
    del f['CFF ']
    if 'VORG' in f: del f['VORG']
    m = f['maxp']; m.tableVersion = 0x00010000
    for k in ('maxZones','maxTwilightPoints','maxStorage','maxFunctionDefs','maxInstructionDefs','maxStackElements','maxSizeOfInstructions','maxComponentElements'):
        setattr(m, k, 0)
    m.maxZones = 1
    f['head'].glyphDataFormat = 0
    f['post'].formatType = 2.0; f['post'].extraNames = []; f['post'].mapping = {}; f['post'].glyphOrder = order
    f.sfntVersion = '\x00\x01\x00\x00'
    f.save(src[:-4] + '.ttf')
    print('ok', src[:-4] + '.ttf')
