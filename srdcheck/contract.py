"""Version identities for the public machine contracts.

Keep these values separate from the package version.  The package can release
compatible fixes without making consumers reinterpret an existing envelope.
"""

import re


_CORE_VERSION_IDENTIFIER = r"(?:0|[1-9][0-9]*)"
_PRERELEASE_IDENTIFIER = (
    r"(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)")
_SEMVER_2_0 = re.compile(
    rf"{_CORE_VERSION_IDENTIFIER}\."
    rf"{_CORE_VERSION_IDENTIFIER}\."
    rf"{_CORE_VERSION_IDENTIFIER}"
    rf"(?:-{_PRERELEASE_IDENTIFIER}"
    rf"(?:\.{_PRERELEASE_IDENTIFIER})*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)


VERDICT_SCHEMA_VERSION = "1.0"
CAPABILITIES_SCHEMA_VERSION = "2.0"
CLAIMS_SCHEMA_VERSION = "1.0"
CORRECTIONS_SCHEMA_VERSION = "1.0"
COMPATIBILITY_WINDOW = "N/N-1"
WHY_STABILITY = "non-contractual"

# Compatibility is release history, not arithmetic: after 0.9, the previous
# shipped minor might be 0.7 rather than an invented 0.8.  Make each new minor
# name its actual predecessor so a version bump cannot silently claim a window
# that has no fixture.
PREVIOUS_ENGINE_MINOR = {"0.6": "0.5"}


def is_semver_2_0(value):
    """Whether *value* is a complete, strict SemVer 2.0 version string.

    Uses only ASCII identifier classes and ``fullmatch``. In particular, core
    and numeric prerelease identifiers reject leading zeroes, while build
    identifiers may contain them as SemVer permits.
    """
    return isinstance(value, str) and _SEMVER_2_0.fullmatch(value) is not None


def engine_minor(version):
    """Return the ``major.minor`` identity from a package version."""
    match = re.match(r"^(\d+)\.(\d+)", version)
    if not match:
        raise ValueError(f"package version has no major.minor identity: {version!r}")
    return f"{match.group(1)}.{match.group(2)}"


def supported_engine_minors(version):
    """The current and immediately previous minor promised by N/N-1."""
    current = engine_minor(version)
    try:
        previous = PREVIOUS_ENGINE_MINOR[current]
    except KeyError as exc:
        raise ValueError(
            f"no previous-minor compatibility identity recorded for {current}; "
            "update PREVIOUS_ENGINE_MINOR and roll the semantic fixture") from exc
    return [current, previous]
