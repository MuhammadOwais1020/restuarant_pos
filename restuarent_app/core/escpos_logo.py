# core/escpos_logo.py

from PIL import Image

def logo_to_escpos_bytes(path_to_logo):
    # 1) Open & convert to 1-bit (monochrome) B/W
    im = Image.open(path_to_logo).convert("L")
    # threshold → pure black or white
    threshold = 128
    im = im.point(lambda px: 0 if px < threshold else 1, mode="1")

    width, height = im.size

    # 2) Pad width so it's divisible by 8
    if width % 8 != 0:
        new_width = width + (8 - (width % 8))
        padded = Image.new("1", (new_width, height), 1)  # fill white (1)
        padded.paste(im, (0, 0))
        im = padded
        width = new_width

    # 3) Build the GS v 0 header for a “normal” raster image (mode=0)
    #    [ GS ] [ 'v' ] [ '0' ] [ m ] [ xL ] [ xH ] [ yL ] [ yH ] [ data... ]
    #    m = 0 → normal (no scaling)
    x_bytes = width // 8
    xL = x_bytes & 0xFF
    xH = (x_bytes >> 8) & 0xFF
    yL = height & 0xFF
    yH = (height >> 8) & 0xFF

    header = b"\x1D\x76\x30" + b"\x00" + bytes([xL, xH, yL, yH])

    # 4) Now emit the bitmap, row by row, 8 pixels per byte
    data = bytearray()
    pix = im.load()
    for y in range(height):
        for byte_idx in range(x_bytes):
            byte = 0
            for bit in range(8):
                pixel = pix[byte_idx * 8 + bit, y]
                # PIL in "1" mode: 0 = black, 255 (or 1) = white
                if pixel == 0:
                    byte |= (1 << (7 - bit))
            data.append(byte)

    return header + bytes(data)
