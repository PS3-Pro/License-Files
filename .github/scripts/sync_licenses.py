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


def get_license_files():
    return sorted([f for f in os.listdir(FILES_DIR) if f.endswith(".rap")])


def create_rap_bin():
    """Generates the consolidated rap.bin container."""
    MAGIC = b"\xFA\xF0\xFA\xF0" + b"\x00" * 12
    PADC = b"\x00" * 12
    all_files = get_license_files()

    with open(RAP_BIN_EXE, "wb") as bf:
        for fn in all_files:
            cid = fn[:-4]
            file_path = os.path.join(FILES_DIR, fn)

            with open(file_path, "rb") as f:
                content = f.read(16)

            if len(content) == 16 and len(cid) == 36:
                bf.write(MAGIC + cid.encode() + PADC + content)


def write_stats(quantity):
    now = datetime.now(timezone.utc)
    label = f"{quantity:,}".replace(",", ".")


    stats = {
        "quantity": quantity,
        "label": label,
        "date": now.strftime("%Y-%m-%d"),
        "updated_at": now.isoformat(),
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

    qty = len(get_license_files())
    write_stats(qty)

    print(f"Sync completed. Total license files: {qty}")


if __name__ == "__main__":
    main()
