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
CATALOG_JSON = ".github/catalog.json"

# Keep this list aligned with every source used by the License Pack.
TSV_SOURCES = [
    {"url": "https://nopaystation.com/tsv/PS3_GAMES.tsv", "type": "game", "label": "Games", "platform": "PS3"},
    {"url": "https://nopaystation.com/tsv/PS3_DLCS.tsv", "type": "dlc", "label": "DLCs", "platform": "PS3"},
    {"url": "https://nopaystation.com/tsv/PS3_THEMES.tsv", "type": "theme", "label": "Themes", "platform": "PS3"},
    {"url": "https://nopaystation.com/tsv/PS3_AVATARS.tsv", "type": "avatar", "label": "Avatars", "platform": "PS3"},
    {"url": "https://nopaystation.com/tsv/PS3_DEMOS.tsv", "type": "demo", "label": "Demos", "platform": "PS3"},
    {"url": "https://nopaystation.com/tsv/PSP_GAMES.tsv", "type": "psp-game", "label": "PSP Games", "platform": "PSP"},
    {"url": "https://nopaystation.com/tsv/PSP_DLCS.tsv", "type": "psp-dlc", "label": "PSP DLCs", "platform": "PSP"},
    {"url": "https://nopaystation.com/tsv/pending/PS3_GAMES.tsv", "type": "game", "label": "Games", "platform": "PS3"},
    {"url": "https://nopaystation.com/tsv/pending/PS3_DLCS.tsv", "type": "dlc", "label": "DLCs", "platform": "PS3"},
    {"url": "https://nopaystation.com/tsv/pending/PS3_THEMES.tsv", "type": "theme", "label": "Themes", "platform": "PS3"},
    {"url": "https://nopaystation.com/tsv/pending/PS3_AVATARS.tsv", "type": "avatar", "label": "Avatars", "platform": "PS3"},
    {"url": "https://nopaystation.com/tsv/pending/PS3_DEMOS.tsv", "type": "demo", "label": "Demos", "platform": "PS3"},
]


def clean_value(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def is_valid_rap(value):
    value = clean_value(value)
    return len(value) >= 32 and re.fullmatch(r"[0-9a-fA-F]+", value) is not None


def repair_mojibake(value):
    text = clean_value(value)
    if not text:
        return ""

    # Legacy strings from older NPS exports / decode paths.
    text = (text
            .replace("Γäó", "™")
            .replace("ΓÇô", "–")
            .replace("ΓÇö", "—")
            .replace("ΓÇÖ", "’"))

    # Repair UTF-8 bytes that were previously decoded as Windows-1252.
    # Run twice so double-mojibake such as "Ã¢â€žÂ¢" also collapses to "™".
    for _ in range(2):
        if not re.search(r"[ÃÂâð]", text):
            break
        try:
            repaired = text.encode("cp1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if repaired == text:
            break
        text = repaired

    # Final targeted fallbacks for malformed legacy strings that cannot be
    # round-tripped as a whole through cp1252.
    return (text
            .replace("â„¢", "™")
            .replace("â€“", "–")
            .replace("â€”", "—")
            .replace("â€™", "’"))


def clean_catalog_name(value):
    return repair_mojibake(value)


def process_tsv(source):
    """Downloads one NPS TSV, refreshes RAP files, and returns catalog rows."""
    url = source["url"]
    catalog_rows = []

    try:
        response = requests.get(url, timeout=30, headers={"User-Agent": "PS3-Pro-License-Sync/2.0"})
        response.raise_for_status()
        try:
            tsv_text = response.content.decode("utf-8-sig")
        except UnicodeDecodeError:
            # Some NPS exports contain Windows-1252 bytes (notably ™).
            # Falling back here prevents one source from aborting the whole
            # catalog update and leaving an old catalog online.
            tsv_text = response.content.decode("cp1252")
        frame = pd.read_csv(StringIO(tsv_text), sep="\t", dtype=str, keep_default_na=False)

        for row in frame.to_dict("records"):
            content_id = clean_value(row.get("Content ID"))
            rap_value = clean_value(row.get("RAP"))

            # Keep the existing License Pack behavior: valid 16-byte RAP values become files.
            if len(content_id) == 36 and is_valid_rap(rap_value):
                file_path = os.path.join(FILES_DIR, f"{content_id}.rap")
                with open(file_path, "wb") as handle:
                    handle.write(binascii.unhexlify(rap_value[:32]))

            name = clean_catalog_name(row.get("Name"))
            title_id = clean_value(row.get("Title ID")).upper()
            region = clean_value(row.get("Region")).upper()

            # A few rows may not expose Title ID, but Content ID still makes them searchable/listable.
            if not name and not title_id and not content_id:
                continue

            not_required = bool(re.search(r"NOT\s+REQUIRED", rap_value, re.IGNORECASE))
            catalog_rows.append({
                "n": name,
                "id": title_id,
                "cid": content_id,
                "r": region,
                "t": source["type"],
                "tl": source["label"],
                "p": source["platform"],
                "nr": 1 if not_required else 0,
            })

    except Exception as exc:
        print(f"Error processing {url}: {exc}")
        return {"ok": False, "rows": [], "url": url}

    return {"ok": True, "rows": catalog_rows, "url": url}


def get_license_files():
    return sorted([name for name in os.listdir(FILES_DIR) if name.lower().endswith(".rap")])


def create_rap_bin():
    """Generates the consolidated rap.bin container."""
    magic = b"\xFA\xF0\xFA\xF0" + b"\x00" * 12
    pad = b"\x00" * 12

    with open(RAP_BIN_EXE, "wb") as output:
        for filename in get_license_files():
            content_id = filename[:-4]
            file_path = os.path.join(FILES_DIR, filename)
            with open(file_path, "rb") as handle:
                content = handle.read(16)
            if len(content) == 16 and len(content_id) == 36:
                output.write(magic + content_id.encode() + pad + content)


def write_stats(quantity, now):
    label = f"{quantity:,}".replace(",", ".")
    stats = {
        "quantity": quantity,
        "label": label,
        "date": now.strftime("%Y-%m-%d"),
        "updated_at": now.isoformat(),
    }
    os.makedirs(os.path.dirname(STATS_JSON), exist_ok=True)
    with open(STATS_JSON, "w", encoding="utf-8") as handle:
        json.dump(stats, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def catalog_key(item):
    # Content ID is the strongest identity. Keep region/type/title in the fallback for rows without one.
    content_id = item.get("cid", "").strip().lower()
    if content_id:
        return ("cid", content_id)
    return (
        "fallback",
        item.get("p", ""),
        item.get("t", ""),
        item.get("id", ""),
        item.get("r", ""),
        item.get("n", "").casefold(),
    )


def write_catalog(all_rows, now):
    # Keep the exact filename so the website can download an individual license without guessing.
    license_file_by_id = {os.path.splitext(name)[0].lower(): name for name in get_license_files()}
    existing_license_ids = set(license_file_by_id)

    # TSV_SOURCES is ordered official first, pending second. setdefault keeps official metadata when duplicated.
    unique = {}
    for item in all_rows:
        unique.setdefault(catalog_key(item), item)

    content = []
    type_counts = {}
    license_count = 0
    missing_count = 0
    not_required_count = 0

    for item in unique.values():
        content_id = item.get("cid", "").strip().lower()
        license_file = license_file_by_id.get(content_id, "") if content_id else ""
        if license_file:
            status = "available"
            license_count += 1
        elif item.get("nr"):
            status = "not-required"
            not_required_count += 1
        else:
            status = "missing"
            missing_count += 1

        item = dict(item)
        item.pop("nr", None)
        item["s"] = status
        if license_file:
            item["f"] = license_file
        content.append(item)
        type_counts[item["t"]] = type_counts.get(item["t"], 0) + 1

    content.sort(key=lambda item: (
        clean_value(item.get("n")).casefold(),
        clean_value(item.get("id")),
        clean_value(item.get("cid")),
    ))

    payload = {
        "updated_at": now.isoformat(),
        "count": len(content),
        "licenses": license_count,
        "missing": missing_count,
        "not_required": not_required_count,
        "types": type_counts,
        "content": content,
    }

    catalog_dir = os.path.dirname(CATALOG_JSON)
    if catalog_dir:
        os.makedirs(catalog_dir, exist_ok=True)
    with open(CATALOG_JSON, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")

    print(
        f"Catalog generated: {len(content)} entries | "
        f"{license_count} with license | {not_required_count} not required | {missing_count} missing"
    )


def main():
    os.makedirs(FILES_DIR, exist_ok=True)
    print("Starting database sync...")

    # executor.map preserves TSV_SOURCES order, so official rows retain priority over pending duplicates.
    with ThreadPoolExecutor(max_workers=5) as executor:
        source_results = list(executor.map(process_tsv, TSV_SOURCES))

    all_catalog_rows = [row for result in source_results for row in result["rows"]]
    failed_sources = [result["url"] for result in source_results if not result["ok"]]
    create_rap_bin()

    now = datetime.now(timezone.utc)
    quantity = len(get_license_files())
    write_stats(quantity, now)
    if failed_sources:
        print("Catalog not replaced because one or more TSV sources failed:")
        for url in failed_sources:
            print(f" - {url}")
    else:
        write_catalog(all_catalog_rows, now)

    print(f"Sync completed. Total license files: {quantity}")


if __name__ == "__main__":
    main()
