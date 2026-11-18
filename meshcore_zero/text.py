"""Text and offline color emoji, with sequence-aware measurement and wrapping."""
from functools import lru_cache
import json
import re
from pathlib import Path
import unicodedata

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).resolve().parents[1] / 'assets/fonts'


@lru_cache(maxsize=1)
def emoji_trie():
    root = {}
    for sequence in json.loads((ASSETS / 'emoji-sequences.json').read_text()):
        node = root
        for char in sequence:
            node = node.setdefault(char, {})
        node[None] = True
    return root


@lru_cache(maxsize=512)
def units(value):
    """Keep flags, modifiers and ZWJ emoji together while laying out text."""
    result = []
    root = emoji_trie()
    i = 0
    while i < len(value):
        node = root
        end = match = i
        while end < len(value) and value[end] in node:
            node = node[value[end]]
            end += 1
            if None in node:
                match = end
        if match > i:
            result.append((value[i:match], True))
            i = match
        else:
            end = i + 1
            while end < len(value) and unicodedata.combining(value[end]):
                end += 1
            result.append((value[i:end], False))
            i = end
    return tuple(result)


class Text:
    def __init__(self, font):
        self.font = font
        self.emoji_font = None

    def width(self, value, size=12, bold=False):
        return sum(self.advance(part,emoji,size,bold)
                   for part, emoji in units(str(value)))

    @lru_cache(maxsize=4096)
    def advance(self, part, emoji, size=12, bold=False):
        return size+1 if emoji else self.font(size,bold).getlength(part)

    @lru_cache(maxsize=256)
    def emoji(self, value, size):
        if self.emoji_font is None:
            self.emoji_font = ImageFont.truetype(str(ASSETS / 'NotoColorEmoji.ttf'),109)
        # CBDT has one fixed bitmap strike. Render at that size, then downsample
        # the complete shaped cluster rather than drawing separate code points.
        width = max(160, int(self.emoji_font.getlength(value)) + 4)
        tile = Image.new('RGBA',(width,160))
        ImageDraw.Draw(tile).text((0,0),value,font=self.emoji_font,
            embedded_color=True,anchor='lt')
        bbox = tile.getbbox()
        glyph = tile.crop(bbox) if bbox else tile
        glyph.thumbnail((size+1,size+1),Image.Resampling.LANCZOS)
        return glyph

    def fit(self, value, width, size=12, bold=False):
        value = str(value).replace('\n',' ')
        if self.width(value,size,bold) <= width:
            return value
        parts = list(units(value))
        while parts and self.width(''.join(p for p,_ in parts)+'…',size,bold) > width:
            parts.pop()
        return ''.join(p for p,_ in parts)+'…' if self.width('…',size,bold) <= width else ''

    def draw(self, image, xy, value, fill, size=12, bold=False, width=None):
        value = str(value).replace('\n',' ')
        if width is not None:
            value = self.fit(value,width,size,bold)
        x,y = xy
        draw = ImageDraw.Draw(image)
        normal=[]
        font=self.font(size,bold)
        options={'features':['-kern']} if font.layout_engine == ImageFont.Layout.RAQM else {}
        def flush():
            nonlocal x
            if normal:
                # Shape/rasterize each contiguous text run once, rather than
                # invoking FreeType separately for every letter.
                draw.text((round(x),y),''.join(normal),font=font,fill=fill,**options)
                x += sum(self.advance(p,False,size,bold) for p in normal)
                normal.clear()
        for part, emoji in units(value):
            if emoji:
                flush()
                glyph = self.emoji(part,size)
                image.paste(glyph,(round(x),round(y+1)),glyph)
                x += size+1
            else:
                normal.append(part)
        flush()
        return x

    def wrap(self, spans, width, size=11):
        """Wrap colored spans into compact rows without splitting emoji clusters."""
        return self._wrap(tuple(spans),width,size)

    @lru_cache(maxsize=512)
    def _wrap(self, spans, width, size):
        rows = [[]]
        used = 0
        for value,color in spans:
            for token in re.findall(r'[^\S\n]+|\n|[^\s]+',value):
                token_width = self.width(token,size)
                if token != '\n' and not token.isspace() and used and used+token_width > width and token_width <= width:
                    rows.append([])
                    used = 0
                for part,emoji in units(token):
                    advance = self.advance(part,emoji,size,False)
                    if part == '\n' or (used+advance > width and rows[-1]):
                        rows.append([])
                        used = 0
                    if part == '\n' or (not rows[-1] and part == ' '):
                        continue
                    if rows[-1] and rows[-1][-1][1] == color:
                        text,_ = rows[-1][-1]
                        rows[-1][-1] = (text+part,color)
                    else:
                        rows[-1].append((part,color))
                    used += advance
        return tuple(tuple(row) for row in rows)
