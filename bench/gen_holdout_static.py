"""Generate isolated synthetic visual grounding holdout; no UI, network or model.

Seed 88931; bounding boxes are pixel [left, top, right, bottom] with right/bottom
exclusive. Handback examples have no target box. Paths are relative to bench/cases.
"""
from __future__ import annotations
import hashlib
import json
import math
import random
from pathlib import Path
import PIL
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'cases' / 'holdout-static'
SEED = 88931
SIZES = [(960, 640), (1280, 800), (1920, 1080)]
FONTS = [Path('C:/Windows/Fonts/segoeui.ttf'), Path('C:/Windows/Fonts/arial.ttf'),
         Path('C:/Windows/Fonts/calibri.ttf')]
PALETTES = [('#f3f7f8', '#19333c', '#ffffff', '#9ab7c0'),
            ('#f9f3e8', '#382d25', '#fffefa', '#c6af94'),
            ('#eef0f8', '#262b43', '#ffffff', '#9ca6c9'),
            ('#eaf5ee', '#1c392b', '#ffffff', '#94b9a1')]
WORDS = ['Inspect Dovetail', 'Open Whimbrel', 'Review Juniper', 'View Thimble',
         'Inspect Marigold', 'Open Kestrel', 'Review Bracken', 'View Saffron']
ABSENT = ['Inspect Umber', 'Open Tern', 'Review Snowdrop', 'View Yarrow',
          'Inspect Mallow', 'Open Redwing', 'Review Nettle', 'View Osprey']
SHAPES = [('blue', '#235ca8', 'circle'), ('orange', '#cb631d', 'square'),
          ('purple', '#713c9e', 'triangle'), ('green', '#228050', 'diamond'),
          ('red', '#b83439', 'hexagon'), ('teal', '#16888e', 'plus')]


def font(rng, size):
    return ImageFont.truetype(str(rng.choice(FONTS)), size=size)


def centered(draw, box, value, fnt, fill):
    x0, y0, x1, y1 = box
    bounds = draw.textbbox((0, 0), value, font=fnt)
    x = x0 + (x1 - x0 - (bounds[2] - bounds[0])) / 2 - bounds[0]
    y = y0 + (y1 - y0 - (bounds[3] - bounds[1])) / 2 - bounds[1]
    draw.text((round(x), round(y)), value, font=fnt, fill=fill)


def box_button(draw, box, color, border, text, fnt, ink):
    draw.rounded_rectangle(box, radius=9, fill=color, outline=border, width=2)
    centered(draw, box, text, fnt, ink)


def symbol(draw, box, shape, color):
    x0, y0, x1, y1 = box
    cx, cy = (x0+x1)/2, (y0+y1)/2
    r = min(x1-x0, y1-y0) * .27
    if shape == 'circle':
        draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill=color)
    elif shape == 'square':
        draw.rectangle((cx-r, cy-r, cx+r, cy+r), fill=color)
    elif shape == 'triangle':
        draw.polygon([(cx, cy-r), (cx+r, cy+r), (cx-r, cy+r)], fill=color)
    elif shape == 'diamond':
        draw.polygon([(cx, cy-r), (cx+r, cy), (cx, cy+r), (cx-r, cy)], fill=color)
    elif shape == 'hexagon':
        draw.polygon([(cx + r*math.cos(math.pi*k/3), cy + r*math.sin(math.pi*k/3)) for k in range(6)], fill=color)
    else:
        draw.rectangle((cx-r*.28, cy-r, cx+r*.28, cy+r), fill=color)
        draw.rectangle((cx-r, cy-r*.28, cx+r, cy+r*.28), fill=color)


def build(index, rng):
    width, height = SIZES[index % len(SIZES)]
    scale = min(width / 960, height / 640)
    bg, ink, card, border = rng.choice(PALETTES)
    image = Image.new('RGB', (width, height), bg)
    draw = ImageDraw.Draw(image)
    title_font = font(rng, round(24*scale))
    button_font = font(rng, round(16*scale))
    small_font = font(rng, round(13*scale))
    draw.text((round(width*.06), round(height*.07)), 'Collection workspace', font=title_font, fill=ink)
    draw.text((round(width*.06), round(height*.14)), 'Choose an available control below.', font=small_font, fill=ink)
    icon_mode = index < 24 and index % 2 == 1
    cols, rows = (3, 2)
    cell_w, cell_h = round(width*.24), round(height*.15)
    margin_x = round(width * rng.uniform(.06, .15))
    margin_y = round(height * rng.uniform(.28, .39))
    gap_x, gap_y = round(width*.03), round(height*.035)
    boxes = [(margin_x + c*(cell_w+gap_x), margin_y + r*(cell_h+gap_y),
              margin_x + c*(cell_w+gap_x) + cell_w, margin_y + r*(cell_h+gap_y) + cell_h)
             for r in range(rows) for c in range(cols)]
    # Convert Pillow's inclusive rectangle drawing to exclusive manifest bounds.
    labels = rng.sample(WORDS, len(boxes))
    if icon_mode:
        icons = rng.sample(SHAPES, len(boxes))
        target = rng.randrange(len(boxes))
        for box, (_, color, shape) in zip(boxes, icons):
            draw.rounded_rectangle((box[0], box[1], box[2]-1, box[3]-1), radius=9, fill=card, outline=border, width=2)
            symbol(draw, box, shape, color)
        color_name, _, shape = icons[target]
        instruction = f'Click the {color_name} {shape} icon.'
        kind = 'positive_icon'
    else:
        target = rng.randrange(len(boxes))
        for box, label in zip(boxes, labels):
            box_button(draw, (box[0], box[1], box[2]-1, box[3]-1), card, border, label, button_font, ink)
        if index < 24:
            instruction = f'Click the button labeled {labels[target]}.'
            kind = 'positive_label'
        elif index < 32:
            instruction = f'Click the button labeled {ABSENT[index-24]}.'
            kind = 'absent_label'
        else:
            instruction = f'Click the button labeled {labels[target]}.'
            kind = 'modal_blocked' if index < 34 else 'disabled'
            if kind == 'modal_blocked':
                # Draw a dimmed, legible background and a foreground blocking dialog.
                veil = Image.new('RGBA', image.size, (20, 20, 28, 105))
                image = Image.alpha_composite(image.convert('RGBA'), veil).convert('RGB')
                draw = ImageDraw.Draw(image)
                modal = (round(width*.30), round(height*.32), round(width*.70), round(height*.68))
                draw.rounded_rectangle(modal, radius=12, fill='#ffffff', outline='#505762', width=3)
                draw.text((modal[0]+round(24*scale), modal[1]+round(26*scale)), 'Session paused', font=title_font, fill='#18202a')
                draw.text((modal[0]+round(24*scale), modal[1]+round(85*scale)), 'Background controls are unavailable.', font=small_font, fill='#18202a')
            else:
                box = boxes[target]
                box_button(draw, (box[0], box[1], box[2]-1, box[3]-1), '#e2e3e4', '#adb0b2', labels[target], button_font, '#777a7b')
                # Explicit visible disabled indicator outside the requested button.
                draw.text((box[0], box[3]+round(4*scale)), 'Unavailable', font=small_font, fill=ink)
    filename = f'case-{index:02d}.png'
    image.save(OUT / filename, format='PNG', optimize=False)
    result = {'id': f'holdout-static-{index:02d}', 'image': f'holdout-static/{filename}',
              'instruction': instruction, 'kind': kind,
              'expected_action': 'click' if index < 24 else 'handback'}
    if index < 24:
        result['bbox'] = list(boxes[target])
    else:
        result['absent'] = True
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    cases = [build(index, rng) for index in range(36)]
    (OUT / 'manifest.json').write_text(json.dumps(cases, indent=2) + '\n', encoding='utf-8')
    audit = {'seed': SEED, 'case_count': len(cases),
             'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'pillow_version': PIL.__version__,
             'font_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in FONTS},
             'counts': {'positive_label': 12, 'positive_icon': 12, 'absent_label': 8, 'modal_blocked': 2, 'disabled': 2},
             'bbox_format': 'left, top, right, bottom in image pixels; right and bottom exclusive',
             'rationale': 'Deterministic synthetic engineering controls and icons, varied layout, canvas, font and palette; labels and absence targets chosen before model predictions. Handback cases represent absent or unavailable targets. No external or user content.',
             'limitations': 'Synthetic still images only; no claim about real applications, dynamic state, or model safety.'}
    (OUT / 'audit.json').write_text(json.dumps(audit, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
