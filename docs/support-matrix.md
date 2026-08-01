# Runtime and platform support

This document is the support policy and the map to its CI evidence. “Supported”
means compatibility defects are accepted and fixed. It does not mean that every
Python and operating-system combination runs the same depth of CI.

## Python runtimes

| Runtime | Support | Continuous evidence |
| --- | --- | --- |
| Python 3.10 | Supported; minimum runtime | Full Ubuntu suite, minimum build/runtime lane, wheel and source-distribution cold installs |
| Python 3.11 | Supported | Full Ubuntu suite |
| Python 3.12 | Supported | Full Ubuntu suite; representative Windows and macOS artifact smoke |
| Python 3.13 | Supported | Full Ubuntu suite, wheel and source-distribution cold installs |
| Python 3.9 and older | Unsupported | Rejected by package metadata (`requires-python = ">=3.10"`) |

srdcheck has no required third-party runtime packages. The `minimum-runtime` CI
job proves that contract on Python 3.10 by building with the exact minimum
declared backend (`setuptools==83.0.0`), installing with `--no-deps` and
`--no-index`, and exercising the installed wheel outside the checkout.

## Operating systems

| Platform | Support | CI contract |
| --- | --- | --- |
| Ubuntu | Supported, full-suite tier | The complete test, provenance, generated-file, golden-verdict, and adapter-conformance suite runs on Python 3.10, 3.11, 3.12, and 3.13. |
| Windows | Supported, smoke tier | Python 3.12 builds and cold-installs both the wheel and source distribution, then runs the platform smoke contract. |
| macOS | Supported, smoke tier | Python 3.12 builds and cold-installs both the wheel and source distribution, then runs the platform smoke contract. |
| Other operating systems | Best effort | No continuous project CI; portable Python defects may still be considered. |

Windows and macOS are deliberately representative smoke lanes, not claims of
full Python-by-OS matrix parity. Python 3.10–3.13 is the runtime support range;
Ubuntu provides exhaustive version evidence, while Python 3.12 provides the
continuous platform evidence for Windows and macOS.

## Platform smoke contract

The same `scripts/cold_artifact_smoke.py` contract runs on all three operating
systems. For every artifact supplied, it:

1. inspects package version, license/NOTICE, adapter attribution, and bundled
   citation text;
2. cold-installs with no dependency resolution or registry access;
3. installs and runs from paths containing spaces and Unicode characters;
4. invokes the installed module CLI and the generated `srdcheck` console entry
   point for citation, jurisdiction, query, capabilities, and a Unicode
   argument;
5. imports and queries the installed library outside the source checkout; and
6. performs an MCP stdio initialize, tool discovery, legal tool call, and
   Unicode refusal call through both the module and generated `srdcheck-mcp`
   console entry point.

The `cold-install` CI job applies this contract to both wheel and source
distribution on the supported Python edges (3.10 and 3.13). The
`platform-smoke` job applies the same two-artifact contract on Windows and
macOS. This keeps the support claim tied to installed public interfaces rather
than a source-tree-only import.

## Build dependency floor

The source distribution requires `setuptools>=83.0.0`. The setuptools 77 line
introduced the PEP 639 `project.license-files` metadata and SPDX license
expression this project uses, but releases before 83 carry a
Unicode-normalization manifest-exclusion vulnerability relevant to source
distributions and macOS filesystems. Version 83.0.0 is published, unyanked,
requires the same Python 3.10 minimum as srdcheck, and is the minimum
safe-and-compatible backend. The dedicated minimum lane uses that exact
version; ordinary and release builds may use newer compatible versions.
