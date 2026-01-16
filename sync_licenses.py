import os
import pandas as pd
import re
import binascii
import requests
from concurrent.futures import ThreadPoolExecutor

FILES_DIR = "files"
RAP_BIN_EXE = "rap.bin"

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
    print(f"🔍 Scaning: {url}")
    try:
        r = requests.get(url, timeout=30)
        from io import StringIO
        df = pd.read_csv(StringIO(r.text), sep="\t")
        
        if "Content ID" in df.columns and "RAP" in df.columns:
            rows = df[df["RAP"].notna() & (df["RAP"].str.len() >= 32)].to_dict('records')
            
            for row in rows:
                cid = str(row["Content ID"]).strip()
                val = str(row["RAP"]).strip()
                
                if re.fullmatch(r"[0-9a-fA-F]+", val):
                    file_path = os.path.join(FILES_DIR, f"{cid}.rap")
                    
                    with open(file_path, "wb") as f:
                        f.write(binascii.unhexlify(val[:32]))
    except Exception as e:
        print(f"❌ Error processing {url}: {e}")

def create_rap_bin():
    print(f"🔑 Updating {RAP_BIN_EXE}...")
    MAGIC = b"\xFA\xF0\xFA\xF0" + b"\x00" * 12
    PADC  = b"\x00" * 12
    
    all_files = sorted([f for f in os.listdir(FILES_DIR) if f.endswith(".rap")])
    
    with open(RAP_BIN_EXE, "wb") as bf:
        for fn in all_files:
            path = os.path.join(FILES_DIR, fn)
            content = open(path, "rb").read(16)
            cid = fn[:-4]
            if len(content) == 16 and len(cid) == 0x24:
                bf.write(MAGIC + cid.encode() + PADC + content)

def main():
    if not os.path.exists(FILES_DIR):
        os.makedirs(FILES_DIR)
    
    print("⬇️ Starting global licenses update...")
    with ThreadPoolExecutor(max_workers=5) as exe:
        exe.map(process_tsv, TSV_URLS)
    
    create_rap_bin()
    
    print(f"✅ Done! Total license files generated: {len(os.listdir(FILES_DIR))}")

if __name__ == "__main__":
    main()