import tarfile
import os
import zlib
import hashlib
import json
from datetime import datetime
import subprocess

SOURCE_DIR = 'src'  # Adjust if your .py files are elsewhere
OUTPUT_IMAGE = 'release/firmware.tar.zlib'
METADATA_FILE = 'release/image-info.json'
DEVICE_TYPE = 'pico'  # Or whatever your target is

def create_tar_archive(source_dir, tar_path):
    with tarfile.open(tar_path, "w") as tar:
        for root, _, files in os.walk(source_dir):
            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    arcname = os.path.relpath(full_path, start=source_dir)
                    tar.add(full_path, arcname=arcname)

def compress_zlib(tar_path, output_path):
    with open(tar_path, 'rb') as f_in:
        data = f_in.read()
        compressed = zlib.compress(data)
    with open(output_path, 'wb') as f_out:
        f_out.write(compressed)
    return compressed

def calculate_sha256(data):
    return hashlib.sha256(data).hexdigest()

def get_version():
    try:
        return subprocess.check_output(['git', 'describe', '--tags', '--always']).decode().strip()
    except Exception:
        return "unknown"

def main():
    temp_tar = 'release/temp_firmware.tar'
    create_tar_archive(SOURCE_DIR, temp_tar)

    compressed_data = compress_zlib(temp_tar, OUTPUT_IMAGE)
    os.remove(temp_tar)

    metadata = {
        "device_type": DEVICE_TYPE,
        "version": get_version(),
        "sha256": calculate_sha256(compressed_data),
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

    with open(METADATA_FILE, 'w') as f:
        json.dump(metadata, f, indent=2)

if __name__ == "__main__":
    main()
