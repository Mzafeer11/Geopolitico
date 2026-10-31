import os
import sys
import urllib.request
import zipfile
import tarfile
import json
import shutil
from pathlib import Path

# Target root directory
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = WORKSPACE_ROOT / "data" / "hgis_datasets"

SUBDIRS = {
    "dare_awmc": DATA_DIR / "dare_awmc",
    "chgis": DATA_DIR / "chgis",
    "hgis_indias": DATA_DIR / "hgis_indias",
    "euratlas_pre1800": DATA_DIR / "euratlas_pre1800"
}

def setup_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name, path in SUBDIRS.items():
        path.mkdir(parents=True, exist_ok=True)

def download_file(url, destination_path, timeout=60):
    print(f"--> Downloading: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AntigravityHGISFetcher/1.0'
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as response, open(destination_path, 'wb') as out_file:
        shutil.copyfileobj(response, out_file)
    print(f"    Saved to: {destination_path} ({os.path.getsize(destination_path)} bytes)")

def extract_archive(archive_path, extract_to):
    archive_str = str(archive_path)
    print(f"--> Extracting {archive_path.name} to {extract_to}...")
    if archive_str.endswith(".zip"):
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        print("    Extraction complete.")
        return True
    elif archive_str.endswith(".tar.gz") or archive_str.endswith(".tgz"):
        with tarfile.open(archive_path, 'r:gz') as tar_ref:
            tar_ref.extractall(extract_to)
        print("    Extraction complete.")
        return True
    else:
        print(f"    Skipping extraction for non-archive file: {archive_path.name}")
        return False

def fetch_dare_and_awmc():
    print("\n==========================================")
    print("1. Fetching DARE & AWMC Roman Empire GIS Data...")
    print("==========================================")
    target_dir = SUBDIRS["dare_awmc"]

    # DARE (Digital Atlas of Roman Empire) vector layers (Klokan Technologies / DARE)
    dare_zip = target_dir / "dare_roman_empire.zip"
    dare_url = "https://github.com/klokantech/roman-empire/archive/refs/heads/master.zip"
    try:
        download_file(dare_url, dare_zip)
        extract_archive(dare_zip, target_dir / "dare")
    except Exception as e:
        print(f"ERROR downloading DARE: {e}")

    # AWMC Open Data repository zip (Ancient World Mapping Center)
    awmc_zip = target_dir / "awmc_geodata.zip"
    awmc_url = "https://github.com/AWMC/geodata/archive/refs/heads/master.zip"
    try:
        download_file(awmc_url, awmc_zip)
        extract_archive(awmc_zip, target_dir / "awmc")
    except Exception as e:
        print(f"ERROR downloading AWMC: {e}")

def fetch_chgis():
    print("\n==========================================")
    print("2. Fetching CHGIS (China Historical GIS pre-1800)...")
    print("==========================================")
    target_dir = SUBDIRS["chgis"]

    chgis_zip = target_dir / "cga_harvard_chgis.zip"
    chgis_url = "https://github.com/cga-harvard/chgis/archive/refs/heads/master.zip"
    try:
        download_file(chgis_url, chgis_zip)
        extract_archive(chgis_zip, target_dir / "chgis")
    except Exception as e:
        print(f"WARNING downloading CHGIS source: {e}")

def fetch_hgis_indias():
    print("\n==========================================")
    print("3. Fetching HGIS de las Indias & World Historical GIS Data (1701-1808)...")
    print("==========================================")
    target_dir = SUBDIRS["hgis_indias"]

    # Historical GIS datasets for colonial and world administrative divisions
    hgis_urls = [
        ("world_historical_gis.zip", "https://github.com/idris-maps/world-historical-gis-data/archive/refs/heads/main.zip"),
        ("world_historical_gis_alt.zip", "https://github.com/idris-maps/world-historical-gis-data/archive/refs/heads/master.zip")
    ]

    for filename, url in hgis_urls:
        out_path = target_dir / filename
        try:
            download_file(url, out_path)
            extract_archive(out_path, target_dir / "hgis_indias")
            break
        except Exception as e:
            print(f"Notice: {url} failed ({e}), trying alternative source...")

def fetch_euratlas_pre1800():
    print("\n==========================================")
    print("4. Fetching Pre-1800 World & European Centennial Basemaps...")
    print("==========================================")
    target_dir = SUBDIRS["euratlas_pre1800"]

    basemaps_zip = target_dir / "historical_basemaps.zip"
    basemaps_url = "https://github.com/aourednik/historical-basemaps/archive/refs/heads/master.zip"
    try:
        download_file(basemaps_url, basemaps_zip)
        extract_archive(basemaps_zip, target_dir / "historical_basemaps")
    except Exception as e:
        print(f"ERROR downloading historical basemaps: {e}")


def generate_dataset_inventory():
    print("\n==========================================")
    print("Generating HGIS Dataset Inventory Report...")
    print("==========================================")
    report = {
        "title": "Pre-1800 HGIS Dataset Inventory",
        "root_directory": str(DATA_DIR),
        "categories": {}
    }

    total_files = 0
    total_size_bytes = 0

    for name, path in SUBDIRS.items():
        cat_files = []
        for file_path in path.rglob("*"):
            if file_path.is_file():
                size = file_path.stat().st_size
                total_files += 1
                total_size_bytes += size
                cat_files.append({
                    "relative_path": str(file_path.relative_to(DATA_DIR)),
                    "size_bytes": size
                })
        report["categories"][name] = {
            "path": str(path),
            "file_count": len(cat_files),
            "files_sample": cat_files[:10]  # top 10 files sample
        }

    report["total_file_count"] = total_files
    report["total_size_mb"] = round(total_size_bytes / (1024 * 1024), 2)

    inventory_file = DATA_DIR / "inventory_report.json"
    with open(inventory_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"Inventory report saved to {inventory_file}")
    print(f"Total downloaded files: {total_files}, Total size: {report['total_size_mb']} MB")

def main():
    print("Starting Download of Pre-1800 HGIS Datasets (referenced in data/Rsearch.txt)...")
    setup_directories()
    fetch_dare_and_awmc()
    fetch_chgis()
    fetch_hgis_indias()
    fetch_euratlas_pre1800()
    generate_dataset_inventory()
    print("\nDownload process completed successfully!")

if __name__ == "__main__":
    main()
