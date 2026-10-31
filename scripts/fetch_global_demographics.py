"""
Fetcher and Spatial Harmonizer for Global Demographic Datasets (Option 1):
1. GeoEPR 2023 (Geo-referencing Ethnic Power Relations, ETH Zurich) - Global ethnic/sectarian settlement polygons.
2. EPR Core 2023 (Ethnic Power Relations, ETH Zurich) - Group population share (`size`) per country & time period.
3. WRP National (World Religion Project / Correlates of War) - National religious composition percentages over time.
"""
import os
import sys
import urllib.request
import shutil
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = WORKSPACE_ROOT / "data" / "demographics"

DATASETS = [
    ("GeoEPR-2023.geojson", [
        "https://icr.ethz.ch/data/epr/geoepr/GeoEPR-2023.geojson",
        "https://icr.ethz.ch/data/epr/geoepr/GeoEPR-2021.geojson"
    ]),
    ("EPR-2023.csv", [
        "https://icr.ethz.ch/data/epr/core/EPR-2023.csv",
        "https://icr.ethz.ch/data/epr/core/EPR-2021.csv"
    ]),
    ("WRP_national.csv", [
        "https://raw.githubusercontent.com/ClaudioRojasMon/apuntes_2025/main/WRP_national.csv"
    ])
]

def download_url(url: str, dest: Path, timeout: int = 90) -> bool:
    print(f"--> Downloading {url} ...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GeopoliticoDemographicsFetcher/1.0"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out)
    size_mb = dest.stat().st_size / (1024 * 1024)
    print(f"    Saved to {dest} ({size_mb:.2f} MB)")
    return dest.stat().st_size > 1000

def main():
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    for target_name, urls in DATASETS:
        dest_path = DEMO_DIR / target_name
        if dest_path.exists() and dest_path.stat().st_size > 10000:
            print(f"[SKIP] {target_name} already exists ({dest_path.stat().st_size / (1024*1024):.2f} MB)")
            continue
        success = False
        for u in urls:
            try:
                if download_url(u, dest_path):
                    success = True
                    break
            except Exception as e:
                print(f"    [WARN] Failed {u}: {e}")
        if not success:
            print(f"    [ERROR] Could not download {target_name}")

if __name__ == "__main__":
    main()

