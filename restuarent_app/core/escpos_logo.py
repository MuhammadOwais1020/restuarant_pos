from PIL import Image

def logo_to_escpos_bytes(path_to_logo):
    # Open the image and convert it to black and white (1-bit)
    im = Image.open(path_to_logo).convert("1")

    # Resize the image to fit the printer's width, typically 384px or 576px for thermal printers.
    target_width = 384  # Adjust this width as per your printer's capability
    width, height = im.size
    if width > target_width:
        aspect_ratio = height / width
        new_height = int(target_width * aspect_ratio)
        im = im.resize((target_width, new_height))

    # Convert image to ESC/POS data format
    x_bytes = (im.width + 7) // 8
    y_bytes = im.height
    image_data = b"\x1D\x76\x30\x00" + bytes([x_bytes & 0xFF, x_bytes >> 8, y_bytes & 0xFF, y_bytes >> 8])

    # Add pixel data (1 bit per pixel)
    pixels = im.load()
    for y in range(im.height):
        for x in range(im.width):
            if pixels[x, y] == 0:  # Black pixel
                image_data += b"\x00"
            else:  # White pixel
                image_data += b"\xFF"

    return image_data
