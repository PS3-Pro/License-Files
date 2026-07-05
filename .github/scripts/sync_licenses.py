import os
import re
import json
import binascii
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from io import StringIO

import pandas as pd
import requests


FILES_DIR = "files"
RAP_BIN_EXE = "rap.bin"
STATS_JSON = ".github/stats.json"

TSV_URLS = [
    "https://nopaystation.com/tsv/PS3_GAMES.tsv",
    "https://nopaystation.com/tsv/PS3_DLCS.tsv",
    "https://nopaystation.com/tsv/PS3_THEMES.tsv",
    "https://nopaystation.com/tsv/PS3_AVATARS.tsv",
    "https://nopaystation.com/tsv/PS3_DEMOS.tsv",
    "https://nopaystation.com/tsv/PSP_GAMES.tsv",
    "https://nopaystation.com/tsv/PSP_DLCS.tsv",
    "https://nopaystation.com/tsv/pending/PS3_GAMES.tsv",
    "https://nopaystation.com/tsv/pending/PS3_DLCS.tsv",
    "https://nopaystation.com/tsv/pending/PS3_THEMES.tsv",
    "https://nopaystation.com/tsv/pending/PS3_AVATARS.tsv",
    "https://nopaystation.com/tsv/pending/PS3_DEMOS.tsv",
]


def process_tsv(url):
    """Downloads TSV data and forces update of license files."""
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()

        df = pd.read_csv(StringIO(r.text), sep="\t")

        if "Content ID" not in df.columns or "RAP" not in df.columns:
            return

        rows = df[df["RAP"].notna() & (df["RAP"].str.len() >= 32)].to_dict("records")

        for row in rows:
            cid = str(row["Content ID"]).strip()
            val = str(row["RAP"]).strip()

            if len(cid) == 36 and re.fullmatch(r"[0-9a-fA-F]+", val):
                file_path = os.path.join(FILES_DIR, f"{cid}.rap")

                with open(file_path, "wb") as f:
                    f.write(binascii.unhexlify(val[:32]))

    except Exception as e:
        print(f"Error processing {url}: {e}")


def is_valid_rap_file(file_path, filename):
    if not os.path.isfile(file_path):
        return False

    if not filename.lower().endswith(".rap"):
        return False

    content_id = os.path.splitext(filename)[0]

    if len(content_id) != 36:
        return False

    return os.path.getsize(file_path) == 16


def is_valid_edat_file(file_path, filename):
    if not os.path.isfile(file_path):
        return False

    if not filename.lower().endswith(".edat"):
        return False

    return os.path.getsize(file_path) > 0


def get_rap_files():
    return sorted(
        filename
        for filename in os.listdir(FILES_DIR)
        if is_valid_rap_file(os.path.join(FILES_DIR, filename), filename)
    )


def get_edat_files():
    return sorted(
        filename
        for filename in os.listdir(FILES_DIR)
        if is_valid_edat_file(os.path.join(FILES_DIR, filename), filename)
    )


def get_license_files():
    return sorted(get_rap_files() + get_edat_files())


def create_rap_bin():
    """Generates the consolidated rap.bin container using RAP files only."""
    magic = b"\xFA\xF0\xFA\xF0" + b"\x00" * 12
    padc = b"\x00" * 12
    all_files = get_rap_files()

    with open(RAP_BIN_EXE, "wb") as bf:
        for filename in all_files:
            content_id = os.path.splitext(filename)[0]
            file_path = os.path.join(FILES_DIR, filename)

            with open(file_path, "rb") as f:
                content = f.read(16)

            bf.write(magic + content_id.encode() + padc + content)


def format_quantity(quantity):
    return f"{quantity:,}".replace(",", ".")


def format_updated_at(dt):
    return dt.strftime("%b %d, %Y")


def write_stats(quantity, rap_quantity, edat_quantity, rap_bin_quantity):
    now = datetime.now(timezone.utc)

    stats = {
        "quantity": quantity,
        "label": format_quantity(quantity),
        "updated_at": format_updated_at(now),
        "rap": rap_quantity,
        "edat": edat_quantity,
        "rap_bin": rap_bin_quantity,
    }

    os.makedirs(os.path.dirname(STATS_JSON), exist_ok=True)

    with open(STATS_JSON, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main():
    if not os.path.exists(FILES_DIR):
        os.makedirs(FILES_DIR)

    print("Starting database sync...")

    with ThreadPoolExecutor(max_workers=5) as exe:
        list(exe.map(process_tsv, TSV_URLS))

    create_rap_bin()

    rap_files = get_rap_files()
    edat_files = get_edat_files()
    license_files = get_license_files()

    write_stats(
        quantity=len(license_files),
        rap_quantity=len(rap_files),
        edat_quantity=len(edat_files),
        rap_bin_quantity=len(rap_files),
    )

    print(f"Sync completed.\nTotal license files: {len(license_files)}")
    print(f"RAP files: {len(rap_files)}")
    print(f"EDAT files: {len(edat_files)}")


if __name__ == "__main__":
    main()
