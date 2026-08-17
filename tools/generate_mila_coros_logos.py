from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUTPUT_DIR = Path(__file__).resolve().parents[1] / "core" / "static" / "core" / "brand" / "coros"
SIZES = (102, 120, 144, 300)


def font(size):
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def render_logo(size):
    scale = 4
    canvas_size = size * scale
    image = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = round(canvas_size * 0.035)
    radius = round(canvas_size * 0.2)
    navy = "#17324D"
    orange = "#F57C20"
    draw.rounded_rectangle(
        (margin, margin, canvas_size - margin, canvas_size - margin),
        radius=radius,
        fill=navy,
    )

    wordmark_font = font(round(canvas_size * 0.29))
    wordmark = "MiLa"
    bounds = draw.textbbox((0, 0), wordmark, font=wordmark_font)
    text_width = bounds[2] - bounds[0]
    text_height = bounds[3] - bounds[1]
    x = (canvas_size - text_width) / 2
    y = (canvas_size - text_height) / 2 - bounds[1] - canvas_size * 0.035
    draw.text((x, y), wordmark, font=wordmark_font, fill="white")

    underline_width = round(text_width * 0.58)
    underline_y = round(y + text_height + canvas_size * 0.09)
    underline_x = round((canvas_size - underline_width) / 2)
    draw.rounded_rectangle(
        (
            underline_x,
            underline_y,
            underline_x + underline_width,
            underline_y + round(canvas_size * 0.035),
        ),
        radius=round(canvas_size * 0.018),
        fill=orange,
    )
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        render_logo(size).save(OUTPUT_DIR / f"mila-coros-{size}x{size}.png", optimize=True)


if __name__ == "__main__":
    main()
