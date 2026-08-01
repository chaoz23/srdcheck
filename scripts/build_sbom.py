#!/usr/bin/env python3
"""Generate a compact SPDX 2.3 JSON SBOM for a built wheel."""

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import zipfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    wheel_bytes = args.wheel.read_bytes()
    wheel_hash = hashlib.sha256(wheel_bytes).hexdigest()
    wheel_sha1 = hashlib.sha1(wheel_bytes).hexdigest()
    with zipfile.ZipFile(args.wheel) as archive:
        files = []
        attributions = []
        for name in sorted(archive.namelist()):
            if name.endswith("/"):
                continue
            payload = archive.read(name)
            digest = hashlib.sha256(payload).hexdigest()
            sha1 = hashlib.sha1(payload).hexdigest()
            if "/adapters/srd-" in name:
                licenses = ["MIT", "CC-BY-4.0"]
            elif "/adapters/toy-tictactoe/" in name:
                licenses = ["MIT", "CC0-1.0"]
            else:
                licenses = ["MIT"]
            files.append({
                "SPDXID": "SPDXRef-File-" + hashlib.sha256(name.encode()).hexdigest()[:16],
                "fileName": name,
                "checksums": [
                    {"algorithm": "SHA1", "checksumValue": sha1},
                    {"algorithm": "SHA256", "checksumValue": digest},
                ],
                "licenseConcluded": " AND ".join(licenses),
                "licenseInfoInFiles": licenses,
                "copyrightText": "NOASSERTION",
            })
            if name.endswith("/manifest.json"):
                manifest = json.loads(payload)
                if manifest.get("attribution"):
                    attributions.append(manifest["attribution"])
    version = args.wheel.name.split("-")[1]
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH", "0"))
    created = datetime.datetime.fromtimestamp(
        epoch, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    package_id = "SPDXRef-Package-srdcheck"
    verification_code = hashlib.sha1(
        "".join(sorted(item["checksums"][0]["checksumValue"]
                       for item in files)).encode()).hexdigest()
    package_license = "MIT AND CC-BY-4.0 AND CC0-1.0"
    document = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"srdcheck-{version}",
        "documentNamespace": f"https://github.com/chaoz23/srdcheck/sbom/{wheel_hash}",
        "creationInfo": {"creators": ["Tool: scripts/build_sbom.py"],
                         "created": created},
        "packages": [{
            "name": "srdcheck", "SPDXID": package_id, "versionInfo": version,
            "packageFileName": args.wheel.name,
            "downloadLocation": "NOASSERTION", "filesAnalyzed": True,
            "packageVerificationCode": {
                "packageVerificationCodeValue": verification_code},
            "licenseConcluded": package_license,
            "licenseDeclared": package_license,
            "licenseInfoFromFiles": ["MIT", "CC-BY-4.0", "CC0-1.0"],
            "copyrightText": "NOASSERTION",
            "attributionTexts": sorted(set(attributions)),
            "checksums": [
                {"algorithm": "SHA1", "checksumValue": wheel_sha1},
                {"algorithm": "SHA256", "checksumValue": wheel_hash},
            ],
        }],
        "files": files,
        "relationships": [
            {"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES",
             "relatedSpdxElement": package_id},
            *[{"spdxElementId": package_id, "relationshipType": "CONTAINS",
               "relatedSpdxElement": item["SPDXID"]} for item in files],
        ],
    }
    args.output.write_text(json.dumps(document, indent=2) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
