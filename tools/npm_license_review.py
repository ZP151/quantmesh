"""Fail-closed license review for the frozen frontend npm closure.

The package lock is the reproducible dependency contract. Ordinary entries
retain their exact version, registry integrity and accepted SPDX checks.
Standard bundled entries additionally require actual locked-parent archive
bytes, complete content/identity coverage and their own accepted SPDX.
Unknown or unproven provenance remains a release failure.
"""

from __future__ import annotations

import base64
import binascii
import gzip
import hashlib
import hmac
import io
import json
import re
import sys
import tarfile
import tempfile
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from time import monotonic as _monotonic
from typing import Any

REPO = Path(__file__).resolve().parents[1]
LOCK = REPO / "frontend" / "package-lock.json"

# Exact expressions currently present in package-lock.json.  These are all
# permissive, attribution/share-compatible, or weak file-level copyleft terms
# already documented in docs/licenses.md.  Expression spelling is deliberate:
# an upstream metadata change must be reviewed, not normalized away.
ALLOWED_LICENSES = frozenset(
    {
        "(MIT OR CC0-1.0)",
        "0BSD",
        "Apache-2.0",
        "BlueOak-1.0.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "CC-BY-4.0",
        "ISC",
        "MIT",
        "MIT-0",
        "MPL-2.0",
        "OFL-1.1",
        "Python-2.0",
    }
)


class FrontendLicenseError(ValueError):
    """The npm lock cannot prove an allowed frontend dependency closure."""


def review_lock_document(
    document: object, *, bundle_archives: Mapping[str, bytes] | None = None
) -> dict[str, dict[str, Any]]:
    if not isinstance(document, dict) or document.get("lockfileVersion") != 3:
        raise FrontendLicenseError("frontend lock must use npm lockfileVersion 3")
    packages = document.get("packages")
    if not isinstance(packages, dict) or "" not in packages:
        raise FrontendLicenseError("frontend lock packages/root entry is absent")

    bundle_proofs = _verify_bundles(packages, bundle_archives)
    inventory: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for path, raw in sorted(packages.items()):
        if path == "":
            continue
        if not isinstance(path, str) or not path.startswith("node_modules/"):
            errors.append(f"{path!r}: dependency path is not under node_modules")
            continue
        if not isinstance(raw, dict):
            errors.append(f"{path}: package metadata is not an object")
            continue
        version = raw.get("version")
        license_name = raw.get("license")
        resolved = raw.get("resolved")
        integrity = raw.get("integrity")
        if not isinstance(version, str) or not version.strip():
            errors.append(f"{path}: exact version is absent")
        if path not in bundle_proofs:
            if not isinstance(resolved, str) or not resolved.startswith(
                "https://registry.npmjs.org/"
            ):
                errors.append(f"{path}: registry resolution is absent or untrusted")
            if not isinstance(integrity, str) or not integrity.startswith("sha512-"):
                errors.append(f"{path}: sha512 integrity is absent")
        if not isinstance(license_name, str) or license_name not in ALLOWED_LICENSES:
            errors.append(f"{path}: license {license_name!r} is not allowed")
        if not errors or not errors[-1].startswith(f"{path}:"):
            inventory[path] = {
                "version": str(version),
                "license": str(license_name),
            }
            if path in bundle_proofs:
                inventory[path]["bundle"] = bundle_proofs[path]

    if errors:
        raise FrontendLicenseError("frontend license review failed:\n" + "\n".join(errors))
    if not inventory:
        raise FrontendLicenseError("frontend dependency inventory is empty")
    return inventory


MAX_COMPRESSED = 16 * 1024 * 1024
MAX_EXPANDED = 32 * 1024 * 1024
MAX_MEMBERS = 1024
CACHE = REPO / "output" / "frontend-license-bundles"
_NAME = r"(?:@[a-z0-9_][a-z0-9._~-]*/)?[a-z0-9_][a-z0-9._~-]*"


def _package_path(path: object) -> str:
    pattern = rf"node_modules/{_NAME}(?:/node_modules/{_NAME})*"
    if not isinstance(path, str) or not re.fullmatch(pattern, path):
        raise FrontendLicenseError("bundle dependency path is not canonical")
    if any(part in {".", ".."} for part in path.split("/")):
        raise FrontendLicenseError("bundle dependency path is ambiguous")
    return path.rsplit("/node_modules/", 1)[-1].removeprefix("node_modules/")


def _registry_url(value: object) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise FrontendLicenseError("bundle parent registry is untrusted")
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError as error:
        raise FrontendLicenseError("bundle parent registry is untrusted") from error
    if (
        not value.startswith("https://registry.npmjs.org/")
        or parsed.scheme != "https"
        or parsed.netloc != "registry.npmjs.org"
        or parsed.query
        or parsed.fragment
        or "\\" in value
        or any(ord(char) < 32 for char in value)
        or ".." in urllib.parse.unquote(parsed.path).split("/")
    ):
        raise FrontendLicenseError("bundle parent registry is untrusted")
    return value


def _digest(raw: dict) -> bytes:
    value = raw.get("integrity")
    try:
        if not isinstance(value, str) or not value.startswith("sha512-"):
            raise ValueError
        decoded = base64.b64decode(value[7:], validate=True)
        if len(decoded) != 64:
            raise ValueError
        return decoded
    except (ValueError, binascii.Error) as error:
        raise FrontendLicenseError("bundle parent sha512 is invalid") from error


def _bundle_spec(packages: dict):
    parents = {}
    children = {}
    for path, raw in packages.items():
        if not isinstance(raw, dict):
            continue
        flag = raw.get("inBundle")
        if flag is not None and flag is not False and flag is not True:
            raise FrontendLicenseError("inBundle must be an exact boolean")
        declaration = raw.get("bundleDependencies")
        if declaration:
            if (
                not isinstance(declaration, list)
                or any(
                    not isinstance(name, str) or not re.fullmatch(_NAME, name)
                    for name in declaration
                )
                or len(set(declaration)) != len(declaration)
            ):
                raise FrontendLicenseError("bundle parent declaration is unsupported")
            _package_path(path)
            if flag is True:
                raise FrontendLicenseError("nested bundles are unsupported")
            parents[path] = raw
        if flag is True:
            _package_path(path)
            parent, marker, name = path.rpartition("/node_modules/")
            if not marker or not re.fullmatch(_NAME, name):
                raise FrontendLicenseError("bundle parent is missing or ambiguous")
            children[path] = (parent, name, raw)
    if not parents and not children:
        return None
    if len(parents) != 1:
        raise FrontendLicenseError("exactly one declared bundle parent is supported")
    parent_path, parent = next(iter(parents.items()))
    _registry_url(parent.get("resolved"))
    _digest(parent)
    if not isinstance(parent.get("version"), str) or not parent["version"].strip():
        raise FrontendLicenseError("bundle parent version is absent")
    if not isinstance(parent.get("license"), str) or parent["license"] not in ALLOWED_LICENSES:
        raise FrontendLicenseError("bundle parent license is not allowed")
    expected = {parent_path + "/node_modules/" + name for name in parent["bundleDependencies"]}
    if set(children) != expected or any(value[0] != parent_path for value in children.values()):
        raise FrontendLicenseError("bundle child coverage is incomplete or unsupported")
    return parent_path, parent, children


def _archive_hash(raw: object, parent: dict) -> bytes:
    if not isinstance(raw, bytes) or len(raw) > MAX_COMPRESSED:
        raise FrontendLicenseError("bundle proof must be bounded raw archive bytes")
    if not hmac.compare_digest(hashlib.sha512(raw).digest(), _digest(parent)):
        raise FrontendLicenseError("bundle parent archive sha512 mismatch")
    return raw


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _manifest(files: dict[str, bytes], path: str) -> dict:
    raw = files.get(path)
    if raw is None or len(raw) > 256 * 1024:
        raise FrontendLicenseError("bundle package manifest is missing or excessive")
    try:
        result = json.loads(raw, object_pairs_hook=_unique_json)
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (ValueError, UnicodeError) as error:
        raise FrontendLicenseError("bundle package manifest is invalid") from error


def _archive_files(raw: bytes) -> dict[str, bytes]:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
            expanded = compressed.read(MAX_EXPANDED + 1)
        if len(expanded) > MAX_EXPANDED:
            raise FrontendLicenseError("bundle expanded archive exceeds its cap")
        files = {}
        paths = {}
        with tarfile.open(fileobj=io.BytesIO(expanded), mode="r:") as archive:
            for index, member in enumerate(archive):
                if index >= MAX_MEMBERS:
                    raise FrontendLicenseError("bundle archive member cap exceeded")
                name = member.name.rstrip("/") if member.isdir() else member.name
                parts = name.split("/")
                if (
                    not name
                    or len(name) > 4096
                    or "\\" in name
                    or ":" in name
                    or any(ord(char) < 32 for char in name)
                    or unicodedata.normalize("NFC", name) != name
                    or parts[0] != "package"
                    or any(
                        part in {"", ".", ".."}
                        or part.endswith((".", " "))
                        or re.fullmatch(
                            r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])", part.split(".")[0]
                        )
                        for part in parts
                    )
                    or not (member.isfile() or member.isdir())
                    or name.casefold() in paths
                ):
                    raise FrontendLicenseError("bundle archive path/type is ambiguous or unsafe")
                paths[name.casefold()] = (name, member.isdir())
                if member.isfile():
                    if member.size < 0 or member.size > MAX_EXPANDED:
                        raise FrontendLicenseError("bundle member size is invalid")
                    stream = archive.extractfile(member)
                    if stream is None:
                        raise FrontendLicenseError("bundle member is unavailable")
                    body = stream.read(member.size + 1)
                    if len(body) != member.size:
                        raise FrontendLicenseError("bundle member size mismatch")
                    files[name] = body
            if any(expanded[archive.offset :]):
                raise FrontendLicenseError("bundle archive has unparsed trailing data")
        for name, _directory in paths.values():
            parts = name.split("/")
            if any(
                (ancestor := paths.get("/".join(parts[:index]).casefold())) and not ancestor[1]
                for index in range(1, len(parts))
            ):
                raise FrontendLicenseError("bundle file/directory alias is unsafe")
        return files
    except (OSError, EOFError, tarfile.TarError, ValueError) as error:
        raise FrontendLicenseError("bundle archive is malformed") from error


def _verify_bundles(packages: dict, archives) -> dict:
    if archives is not None and not isinstance(archives, Mapping):
        raise FrontendLicenseError("bundle proof must be a raw archive bytes mapping")
    spec = _bundle_spec(packages)
    if spec is None:
        if archives:
            raise FrontendLicenseError("unexpected bundle archive proof")
        return {}
    parent_path, parent, children = spec
    if not isinstance(archives, Mapping) or set(archives) != {parent_path}:
        raise FrontendLicenseError("exact raw parent archive proof is required")
    raw = _archive_hash(archives[parent_path], parent)
    files = _archive_files(raw)
    outer = _manifest(files, "package/package.json")
    if (
        outer.get("name") != _package_path(parent_path)
        or outer.get("version") != parent["version"]
        or outer.get("license") != parent["license"]
    ):
        raise FrontendLicenseError("bundle parent identity differs from lock")
    declared = outer.get("bundleDependencies", outer.get("bundledDependencies"))
    if (
        "bundleDependencies" in outer
        and "bundledDependencies" in outer
        and outer["bundleDependencies"] != outer["bundledDependencies"]
    ):
        raise FrontendLicenseError("actual bundle declaration aliases conflict")
    if (
        not isinstance(declared, list)
        or any(not isinstance(name, str) for name in declared)
        or len(set(declared)) != len(declared)
        or set(declared) != set(parent["bundleDependencies"])
    ):
        raise FrontendLicenseError("actual bundle declaration differs from lock")
    expected_roots = {"package/node_modules/" + name for name in declared}
    for path in files:
        if path.startswith("package/node_modules/"):
            owner = next((root for root in expected_roots if path.startswith(root + "/")), None)
            if owner is None or "/node_modules/" in path[len(owner) :]:
                raise FrontendLicenseError("unlisted or nested bundle content is unsupported")
    actual_roots = {
        path.removesuffix("/package.json")
        for path in files
        if re.fullmatch(rf"package/(?:node_modules/{_NAME}/)+package\.json", path)
    }
    if actual_roots != expected_roots:
        raise FrontendLicenseError("actual embedded package coverage differs from lock")
    evidence = {}
    for path, (_parent, name, child) in children.items():
        if child.get("resolved") or child.get("integrity"):
            raise FrontendLicenseError("bundle child has invented independent artifact metadata")
        prefix = "package/node_modules/" + name + "/"
        inside = _manifest(files, prefix + "package.json")
        if inside.get("bundleDependencies") or inside.get("bundledDependencies"):
            raise FrontendLicenseError("actual nested bundles are unsupported")
        if inside.get("name") != name or inside.get("version") != child.get("version"):
            raise FrontendLicenseError("actual bundle child identity differs from lock")
        if (
            not isinstance(inside.get("license"), str)
            or inside["license"] not in ALLOWED_LICENSES
            or inside.get("license") != child.get("license")
        ):
            raise FrontendLicenseError("actual bundle child SPDX is absent, disallowed or differs")
        inventory = [
            {
                "path": item[len(prefix) :],
                "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
            }
            for item, body in sorted(files.items())
            if item.startswith(prefix)
        ]
        notices = [
            item["path"]
            for item in inventory
            if "/" not in item["path"]
            and re.match(r"(?i)(license|copying|copyright)", item["path"])
        ]
        evidence[path] = {
            "parent": parent_path,
            "parent_integrity": parent["integrity"],
            "files": inventory,
            "inventory_sha256": hashlib.sha256(
                json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "license_files": notices,
            "notice_qualification": (
                "NOTICE_BODY_PRESENT_ONLY"
                if notices
                else "NOT_QUALIFIED_FOR_FULL_NOTICE_REDISTRIBUTION"
            ),
        }
    return evidence


class _RejectRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise FrontendLicenseError("bundle registry redirects are refused")


def _download_archive(url: str) -> bytes:
    _registry_url(url)
    # No proxy/authentication/environment credential discovery; normal TLS verification.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _RejectRedirect())
    deadline = _monotonic() + 30
    try:
        with opener.open(url, timeout=30) as response:
            if response.geturl() != url:
                raise FrontendLicenseError("bundle registry redirect is untrusted")
            body = bytearray()
            while True:
                if _monotonic() > deadline:
                    raise FrontendLicenseError("bundle download deadline exceeded")
                chunk = response.read1(min(65536, MAX_COMPRESSED - len(body) + 1))
                if not chunk:
                    break
                body.extend(chunk)
                if len(body) > MAX_COMPRESSED:
                    raise FrontendLicenseError("bundle compressed archive exceeds its cap")
            raw = bytes(body)
    except FrontendLicenseError:
        raise
    except (OSError, ValueError) as error:
        raise FrontendLicenseError("bundle registry artifact could not be read") from error
    if len(raw) > MAX_COMPRESSED:
        raise FrontendLicenseError("bundle compressed archive exceeds its cap")
    return raw


def load_bundle_archives(document: object, *, cache_dir: Path = CACHE) -> dict[str, bytes]:
    if not isinstance(document, dict) or not isinstance(document.get("packages"), dict):
        raise FrontendLicenseError("frontend lock packages are absent")
    spec = _bundle_spec(document["packages"])
    if spec is None:
        return {}
    parent_path, parent, _children = spec
    cache_dir = Path(cache_dir)
    if cache_dir.is_symlink():
        raise FrontendLicenseError("bundle cache directory must not be a link")
    path = cache_dir / (_digest(parent).hex() + ".tgz")
    if path.is_symlink():
        raise FrontendLicenseError("bundle cache artifact must not be a link")
    if path.exists():
        with path.open("rb") as stream:
            raw = stream.read(MAX_COMPRESSED + 1)
        return {parent_path: _archive_hash(raw, parent)}
    raw = _archive_hash(_download_archive(parent["resolved"]), parent)
    cache_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=cache_dir, prefix="bundle-", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(raw)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return {parent_path: raw}


def main() -> int:
    try:
        document: Any = json.loads(LOCK.read_text(encoding="utf-8"))
        archives = load_bundle_archives(document)
        inventory = review_lock_document(document, bundle_archives=archives)
    except (OSError, json.JSONDecodeError, FrontendLicenseError) as error:
        print(error, file=sys.stderr)
        return 1

    counts = Counter(item["license"] for item in inventory.values())
    summary = ", ".join(f"{name}={count}" for name, count in sorted(counts.items()))
    print(f"frontend licenses allowed: {len(inventory)} locked packages ({summary})")
    for path, entry in inventory.items():
        if "bundle" in entry:
            print(f"{path}: {entry['bundle']['notice_qualification']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
