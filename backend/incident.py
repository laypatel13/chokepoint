"""The Sept 8, 2025 npm compromise, as recorded in public data.

The 18 malicious versions published from the phished npm account @qix. Every entry has an
OSV malware advisory (MAL-2025-46966 ... MAL-2025-46983); `tools.incident` re-checks each one
against OSV at runtime and takes publish times from the npm registry, so nothing here is a
claim the app makes on its own. The account username is the only personal data involved.
"""

from __future__ import annotations

ACCOUNT = "qix"

COMPROMISED: dict[str, str] = {
    "ansi-regex": "6.2.1",
    "ansi-styles": "6.2.2",
    "backslash": "0.2.1",
    "chalk": "5.6.1",
    "chalk-template": "1.1.1",
    "color-convert": "3.1.1",
    "color-name": "2.0.1",
    "color-string": "2.1.1",
    "debug": "4.4.2",
    "error-ex": "1.3.3",
    "has-ansi": "6.0.1",
    "is-arrayish": "0.3.3",
    "simple-swizzle": "0.2.3",
    "slice-ansi": "7.1.1",
    "strip-ansi": "7.1.1",
    "supports-color": "10.2.1",
    "supports-hyperlinks": "4.1.1",
    "wrap-ansi": "9.0.1",
}

# The replay project: webpack-dev-server exactly as its repository stood before the attack.
# fa9195c (2025-08-25) is the last commit that touched package-lock.json before Sept 8.
REPLAY_REPO = "webpack/webpack-dev-server"
REPLAY_REF = "fa9195cbd6a61a5c970afd84081964276d872c55"
REPLAY_AS_OF = "2025-08-25"
REPLAY_PROJECT = f"{REPLAY_REPO}@{REPLAY_REF[:7]}"
