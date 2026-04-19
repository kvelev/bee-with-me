"""
Download BG Mountains tiles from bgmtile.kade.si for offline use.

Tiles are saved to backend/tiles/bgmountains/{z}/{x}/{y}.png
and served by the FastAPI backend at /tiles/bgmountains/{z}/{x}/{y}.png

Usage:
    python tools/download_tiles.py               # default: z8-z14, full Bulgaria
    python tools/download_tiles.py --min-zoom 10 --max-zoom 16
    python tools/download_tiles.py --bbox 23.0 41.5 24.5 42.5  # lon_min lat_min lon_max lat_max

The server enforces a short delay between requests to avoid hammering the tile server.
Already-downloaded tiles are skipped (safe to re-run / resume).
"""

import argparse
import math
import os
import time
import urllib.request

SOURCE_URL   = 'https://bgmtile.kade.si/{z}/{x}/{y}.png'
OUTPUT_DIR   = 'tiles/bgmountains'
DELAY_SEC    = 0.01   # 50 ms between requests (~100 req/s)

# Bounding box for Bulgarian mountains (conservative — covers all of Bulgaria)
DEFAULT_LON_MIN = 22.3
DEFAULT_LAT_MIN = 41.2
DEFAULT_LON_MAX = 28.7
DEFAULT_LAT_MAX = 44.3

DEFAULT_MIN_ZOOM = 8
DEFAULT_MAX_ZOOM = 18


def lon_to_tile_x(lon: float, zoom: int) -> int:
    return int((lon + 180.0) / 360.0 * (1 << zoom))


def lat_to_tile_y(lat: float, zoom: int) -> int:
    lat_r = math.radians(lat)
    return int((1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * (1 << zoom))


def count_tiles(lon_min, lat_min, lon_max, lat_max, min_zoom, max_zoom):
    total = 0
    for z in range(min_zoom, max_zoom + 1):
        x0 = lon_to_tile_x(lon_min, z)
        x1 = lon_to_tile_x(lon_max, z)
        y0 = lat_to_tile_y(lat_max, z)   # note: lat_max → smaller y
        y1 = lat_to_tile_y(lat_min, z)
        total += (x1 - x0 + 1) * (y1 - y0 + 1)
    return total


def download_tiles(lon_min, lat_min, lon_max, lat_max, min_zoom, max_zoom):
    total    = count_tiles(lon_min, lat_min, lon_max, lat_max, min_zoom, max_zoom)
    done     = 0
    skipped  = 0
    errors   = 0

    print(f'Tiles to fetch: {total:,}  (skipping already downloaded)')
    print(f'Output: {OUTPUT_DIR}')
    print()

    for z in range(min_zoom, max_zoom + 1):
        x0 = lon_to_tile_x(lon_min, z)
        x1 = lon_to_tile_x(lon_max, z)
        y0 = lat_to_tile_y(lat_max, z)
        y1 = lat_to_tile_y(lat_min, z)

        for x in range(x0, x1 + 1):
            dir_path = os.path.join(OUTPUT_DIR, str(z), str(x))
            os.makedirs(dir_path, exist_ok=True)

            for y in range(y0, y1 + 1):
                out_path = os.path.join(dir_path, f'{y}.png')
                done += 1

                if os.path.exists(out_path):
                    skipped += 1
                    continue

                url = SOURCE_URL.format(z=z, x=x, y=y)
                try:
                    req = urllib.request.Request(url, headers={'User-Agent': 'BeeWithMe-TileDownloader/1.0'})
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        status = resp.status
                        data   = resp.read()
                    if status == 200 and len(data) > 67:
                        with open(out_path, 'wb') as f:
                            f.write(data)
                    time.sleep(DELAY_SEC)
                except urllib.error.HTTPError as e:
                    if e.code != 404:
                        errors += 1
                        if errors <= 10:
                            print(f'  ERROR z={z} x={x} y={y}: {e}')
                except Exception as e:
                    errors += 1
                    if errors <= 10:
                        print(f'  ERROR z={z} x={x} y={y}: {e}')

                if done % 100 == 0 or done == total:
                    pct = done / total * 100
                    print(f'  {done:>6}/{total}  ({pct:.1f}%)  skipped={skipped}  errors={errors}', end='\r')

    print(f'\nDone. Downloaded {done - skipped - errors:,}, skipped {skipped:,}, errors {errors:,}')


def main():
    parser = argparse.ArgumentParser(description='Download BG Mountains tiles for offline use')
    parser.add_argument('--bbox', nargs=4, type=float,
                        metavar=('LON_MIN', 'LAT_MIN', 'LON_MAX', 'LAT_MAX'),
                        default=[DEFAULT_LON_MIN, DEFAULT_LAT_MIN, DEFAULT_LON_MAX, DEFAULT_LAT_MAX])
    parser.add_argument('--min-zoom', type=int, default=DEFAULT_MIN_ZOOM)
    parser.add_argument('--max-zoom', type=int, default=DEFAULT_MAX_ZOOM)
    args = parser.parse_args()

    lon_min, lat_min, lon_max, lat_max = args.bbox
    download_tiles(lon_min, lat_min, lon_max, lat_max, args.min_zoom, args.max_zoom)


if __name__ == '__main__':
    main()
