"""Export per-ward screenshots of the single-stair zoning map into a ZIP."""

import argparse
import time
import zipfile
from pathlib import Path

from playwright.sync_api import sync_playwright

# Viewport for per-ward screenshots (landscape)
WARD_VIEWPORT = {"width": 1920, "height": 1080}

# Viewport for full-city screenshot (portrait, sized to fit Chicago tightly)
CITY_VIEWPORT = {"width": 1400, "height": 1800}
CITY_SCALE = 2.8  # higher scale to push file size close to 10 MB

WAIT_FOR_MAP_JS = """
() => {
    const el = document.querySelector('.folium-map');
    if (!el || !el._leaflet_id) return false;
    for (const key of Object.keys(window)) {
        if (window[key] instanceof L.Map) return true;
    }
    return false;
}
"""

TILE_LOAD_TRACKING_JS = """
() => {
    window.__tilesLoaded = true;
    for (const key of Object.keys(window)) {
        const obj = window[key];
        if (obj instanceof L.Map) {
            obj.eachLayer(layer => {
                if (layer instanceof L.TileLayer) {
                    layer.on('loading', () => { window.__tilesLoaded = false; });
                    layer.on('load',    () => { window.__tilesLoaded = true;  });
                }
            });
            break;
        }
    }
}
"""

FIT_TO_CONTENT_JS = """
() => {
    let map;
    for (const key of Object.keys(window)) {
        if (window[key] instanceof L.Map) { map = window[key]; break; }
    }
    // Enable fractional zoom so fitBounds can fill the viewport tightly
    map.options.zoomSnap = 0;
    map.options.zoomDelta = 0.1;
    let allBounds = null;
    map.eachLayer(layer => {
        if (layer.getBounds && typeof layer.getBounds === 'function') {
            try {
                const b = layer.getBounds();
                if (b.isValid()) {
                    if (allBounds) allBounds.extend(b);
                    else allBounds = L.latLngBounds(b.getSouthWest(), b.getNorthEast());
                }
            } catch(e) {}
        }
    });
    if (allBounds) map.fitBounds(allBounds, {padding: [30, 30]});
}
"""


def wait_for_tiles(page, timeout_ms=15000):
    """Wait for map tiles to finish loading, then pause for rendering."""
    try:
        page.wait_for_function("window.__tilesLoaded === true", timeout=timeout_ms)
    except Exception:
        page.wait_for_load_state("networkidle")
    time.sleep(0.5)


def init_page(browser, html_path, viewport, scale_factor):
    """Create a page, load the map, and set up tile tracking."""
    context = browser.new_context(
        viewport=viewport, device_scale_factor=scale_factor,
    )
    page = context.new_page()
    page.goto(f"file://{html_path}", wait_until="networkidle")
    page.wait_for_function(WAIT_FOR_MAP_JS, timeout=30000)
    page.evaluate(TILE_LOAD_TRACKING_JS)
    wait_for_tiles(page)
    return page, context


def export_screenshots(
    html_file="single_stair_map.html",
    output_dir="screenshots",
    output_zip="ward_screenshots.zip",
    image_format="png",
    scale_factor=2,
    ward_subset=None,
):
    html_path = Path(html_file).resolve()
    if not html_path.exists():
        raise FileNotFoundError(f"Map file not found: {html_path}")

    out_dir = Path(output_dir)
    out_dir.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # --- Full city screenshot (large portrait viewport) ---
        print(f"Loading {html_path.name} for full city view...")
        page, ctx = init_page(browser, html_path, CITY_VIEWPORT, CITY_SCALE)
        page.locator("#ward-select").select_option("all")
        page.evaluate(FIT_TO_CONTENT_JS)
        time.sleep(0.3)
        wait_for_tiles(page)
        full_path = out_dir / f"all_wards.{image_format}"
        page.screenshot(path=str(full_path), type=image_format)
        print(f"  Saved: {full_path.name}")
        ctx.close()

        # --- Per-ward screenshots (standard landscape viewport) ---
        print(f"Loading {html_path.name} for ward views...")
        page, ctx = init_page(browser, html_path, WARD_VIEWPORT, scale_factor)
        select = page.locator("#ward-select")

        wards = ward_subset or list(range(1, 51))
        for ward_num in wards:
            select.select_option(str(ward_num))
            time.sleep(0.3)  # zoom animation
            wait_for_tiles(page)

            filename = f"ward_{ward_num:02d}.{image_format}"
            page.screenshot(path=str(out_dir / filename), type=image_format)
            print(f"  Saved: {filename} ({wards.index(ward_num) + 1}/{len(wards)})")

        ctx.close()
        browser.close()

    # Package into ZIP
    zip_path = Path(output_zip)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for img_file in sorted(out_dir.glob(f"*.{image_format}")):
            zf.write(img_file, img_file.name)
        zf.write(html_path, html_path.name)

    total = len(list(out_dir.glob(f"*.{image_format}")))
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"\nDone! {total} screenshots + HTML -> {zip_path} ({size_mb:.1f} MB)")


def main():
    parser = argparse.ArgumentParser(
        description="Export per-ward screenshots of the single-stair zoning map."
    )
    parser.add_argument("--html-file", default="single_stair_map.html",
                        help="Path to the map HTML file")
    parser.add_argument("--output-dir", default="screenshots",
                        help="Directory for individual screenshot files")
    parser.add_argument("--output-zip", default="ward_screenshots.zip",
                        help="Output ZIP file path")
    parser.add_argument("--format", choices=["png", "jpeg"], default="png",
                        help="Image format (default: png)")
    parser.add_argument("--scale", type=int, default=2,
                        help="Device scale factor for retina output (default: 2)")
    parser.add_argument("--wards", type=str, default=None,
                        help="Comma-separated ward numbers to export (default: all 1-50)")
    args = parser.parse_args()

    ward_subset = None
    if args.wards:
        ward_subset = [int(w.strip()) for w in args.wards.split(",")]

    export_screenshots(
        html_file=args.html_file,
        output_dir=args.output_dir,
        output_zip=args.output_zip,
        image_format=args.format,
        scale_factor=args.scale,
        ward_subset=ward_subset,
    )


if __name__ == "__main__":
    main()
