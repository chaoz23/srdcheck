#!/usr/bin/env python3
"""Normalize sdist archive metadata for byte-reproducible tagged builds."""

import argparse
import copy
import gzip
import os
import pathlib
import tarfile
import tempfile


def normalize(path, epoch):
    path = path.resolve()
    temporary = tempfile.NamedTemporaryFile(
        prefix=path.name + ".", suffix=".tmp", dir=path.parent, delete=False)
    temporary_path = pathlib.Path(temporary.name)
    try:
        with temporary, tarfile.open(path, "r:gz") as source:
            with gzip.GzipFile(filename="", mode="wb", fileobj=temporary,
                               compresslevel=9, mtime=epoch) as compressed:
                with tarfile.open(fileobj=compressed, mode="w",
                                  format=tarfile.PAX_FORMAT) as target:
                    for original in source.getmembers():
                        member = copy.copy(original)
                        member.mtime = epoch
                        member.uid = member.gid = 0
                        member.uname = member.gname = ""
                        member.pax_headers = {}
                        payload = source.extractfile(original) if original.isfile() else None
                        target.addfile(member, payload)
        os.chmod(temporary_path, path.stat().st_mode)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
    print(f"normalized sdist: {path.name} (epoch {epoch})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("artifacts", nargs="+", type=pathlib.Path)
    parser.add_argument(
        "--epoch", type=int,
        default=int(os.environ.get("SOURCE_DATE_EPOCH", "0")),
    )
    args = parser.parse_args()
    for artifact in args.artifacts:
        normalize(artifact, args.epoch)


if __name__ == "__main__":
    main()
