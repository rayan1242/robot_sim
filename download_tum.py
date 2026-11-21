"""Download TUM freiburg1_xyz (~0.5 GB); extract RGB and ground truth only."""
from pathlib import Path, PurePosixPath
import shutil
import os
import subprocess
import tarfile
import urllib.request


def main():
    root = Path("data")
    root.mkdir(exist_ok=True)
    archive = root / "rgbd_dataset_freiburg1_xyz.tgz"
    url = "https://cvg.cit.tum.de/rgbd/dataset/freiburg1/rgbd_dataset_freiburg1_xyz.tgz"
    if not archive.exists():
        temporary = archive.with_suffix(".part")
        print(f"Downloading {url}", flush=True)
        if os.name == "nt":
            # Windows curl uses the system certificate store (Schannel).
            subprocess.run(["curl.exe", "--fail", "--location", "--retry", "2",
                            "--output", str(temporary), url], check=True)
        else:
            with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as handle:
                shutil.copyfileobj(response, handle)
        temporary.replace(archive)
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle:
            parts = PurePosixPath(member.name).parts
            if not parts or parts[0] != "rgbd_dataset_freiburg1_xyz":
                continue
            if not member.isfile() or ".." in parts or any(":" in p or "\\" in p for p in parts):
                continue
            if not ((len(parts) == 2 and parts[1] in ("rgb.txt", "groundtruth.txt")) or
                    (len(parts) == 3 and parts[1] == "rgb" and parts[2].endswith(".png"))):
                continue
            target = root.joinpath(*parts)
            if not target.resolve().is_relative_to(root.resolve()):
                raise ValueError("Unsafe archive path")
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.extractfile(member) as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)
    print("Ready: data/rgbd_dataset_freiburg1_xyz (RGB only; depth is not used)")


if __name__ == "__main__":
    main()
