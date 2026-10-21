"""Deterministic frontend dependency security gates."""

from __future__ import annotations

import base64
import copy
import gzip
import hashlib
import importlib.util
import io
import json
import tarfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LOCK = REPO / "frontend" / "package-lock.json"
MANIFEST = REPO / "frontend" / "package.json"
REVIEW = REPO / "tools" / "npm_license_review.py"


def _review_module():
    spec = importlib.util.spec_from_file_location("npm_license_review", REVIEW)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frozen_frontend_lock_has_only_allowed_licenses() -> None:
    review = _review_module()
    document = json.loads(LOCK.read_text(encoding="utf-8"))

    # Actual artifact qualification, separate from the offline synthetic cases below.
    archives = review.load_bundle_archives(document)
    inventory = review.review_lock_document(document, bundle_archives=archives)

    assert len(inventory) == 278
    assert set(inventory) == EXPECTED_LOCK_MEMBERS
    assert set(document["packages"]) - {""} == EXPECTED_LOCK_MEMBERS
    assert inventory["node_modules/react"]["license"] == "MIT"


def test_direct_frontend_dependencies_are_platform_neutral() -> None:
    """A frozen install must work on every CI and operator platform."""

    document = json.loads(LOCK.read_text(encoding="utf-8"))
    packages = document["packages"]
    root = packages[""]
    direct = {
        *root.get("dependencies", {}),
        *root.get("devDependencies", {}),
    }

    constrained = {
        name: {
            key: packages[f"node_modules/{name}"][key]
            for key in ("os", "cpu")
            if key in packages[f"node_modules/{name}"]
        }
        for name in direct
        if any(key in packages[f"node_modules/{name}"] for key in ("os", "cpu"))
    }

    assert constrained == {}


def test_frontend_declares_the_ci_supported_node_floor() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert manifest["engines"]["node"] == "^20.19.0 || >=22.12.0"
    assert (REPO / ".nvmrc").read_text(encoding="utf-8").strip() == "22.12.0"
    assert 'node-version: "22.12.0"' in ci


@pytest.mark.parametrize("license_name", [None, "GPL-3.0-only", "SEE LICENSE IN X"])
def test_frontend_license_review_fails_closed(license_name: str | None) -> None:
    review = _review_module()
    package = {
        "name": "unsafe",
        "version": "1.0.0",
        "resolved": "https://registry.npmjs.org/unsafe/-/unsafe-1.0.0.tgz",
        "integrity": "sha512-test",
    }
    if license_name is not None:
        package["license"] = license_name
    document = {
        "lockfileVersion": 3,
        "packages": {"": {}, "node_modules/unsafe": package},
    }

    with pytest.raises(review.FrontendLicenseError):
        review.review_lock_document(document)


def test_frontend_audit_and_license_review_are_release_and_ci_gates() -> None:
    release_gate = (REPO / "tools" / "release_gate.py").read_text(encoding="utf-8")
    ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    security = (REPO / ".github" / "workflows" / "security.yml").read_text(encoding="utf-8")

    for surface in (release_gate, ci, security):
        assert "npm_license_review.py" in surface
        assert "npm audit --audit-level=high" in surface
    assert "frontend/package.json" in security
    assert "frontend/package-lock.json" in security


# Synthetic archive tests are offline software checks. The frozen-lock test above
# separately qualifies the actual registry artifact when the real lock needs it.
EXPECTED_LOCK_MEMBERS = frozenset(
    {
        "node_modules/@adobe/css-tools",
        "node_modules/@asamuzakjp/css-color",
        "node_modules/@asamuzakjp/css-color/node_modules/lru-cache",
        "node_modules/@babel/code-frame",
        "node_modules/@babel/helper-validator-identifier",
        "node_modules/@babel/runtime",
        "node_modules/@base-ui/react",
        "node_modules/@base-ui/utils",
        "node_modules/@csstools/color-helpers",
        "node_modules/@csstools/css-calc",
        "node_modules/@csstools/css-color-parser",
        "node_modules/@csstools/css-parser-algorithms",
        "node_modules/@csstools/css-tokenizer",
        "node_modules/@esbuild/aix-ppc64",
        "node_modules/@esbuild/android-arm",
        "node_modules/@esbuild/android-arm64",
        "node_modules/@esbuild/android-x64",
        "node_modules/@esbuild/darwin-arm64",
        "node_modules/@esbuild/darwin-x64",
        "node_modules/@esbuild/freebsd-arm64",
        "node_modules/@esbuild/freebsd-x64",
        "node_modules/@esbuild/linux-arm",
        "node_modules/@esbuild/linux-arm64",
        "node_modules/@esbuild/linux-ia32",
        "node_modules/@esbuild/linux-loong64",
        "node_modules/@esbuild/linux-mips64el",
        "node_modules/@esbuild/linux-ppc64",
        "node_modules/@esbuild/linux-riscv64",
        "node_modules/@esbuild/linux-s390x",
        "node_modules/@esbuild/linux-x64",
        "node_modules/@esbuild/netbsd-arm64",
        "node_modules/@esbuild/netbsd-x64",
        "node_modules/@esbuild/openbsd-arm64",
        "node_modules/@esbuild/openbsd-x64",
        "node_modules/@esbuild/openharmony-arm64",
        "node_modules/@esbuild/sunos-x64",
        "node_modules/@esbuild/win32-arm64",
        "node_modules/@esbuild/win32-ia32",
        "node_modules/@esbuild/win32-x64",
        "node_modules/@floating-ui/core",
        "node_modules/@floating-ui/dom",
        "node_modules/@floating-ui/react-dom",
        "node_modules/@floating-ui/utils",
        "node_modules/@fontsource-variable/geist",
        "node_modules/@jridgewell/gen-mapping",
        "node_modules/@jridgewell/remapping",
        "node_modules/@jridgewell/resolve-uri",
        "node_modules/@jridgewell/sourcemap-codec",
        "node_modules/@jridgewell/trace-mapping",
        "node_modules/@oxc-project/types",
        "node_modules/@oxlint/binding-android-arm-eabi",
        "node_modules/@oxlint/binding-android-arm64",
        "node_modules/@oxlint/binding-darwin-arm64",
        "node_modules/@oxlint/binding-darwin-x64",
        "node_modules/@oxlint/binding-freebsd-x64",
        "node_modules/@oxlint/binding-linux-arm-gnueabihf",
        "node_modules/@oxlint/binding-linux-arm-musleabihf",
        "node_modules/@oxlint/binding-linux-arm64-gnu",
        "node_modules/@oxlint/binding-linux-arm64-musl",
        "node_modules/@oxlint/binding-linux-ppc64-gnu",
        "node_modules/@oxlint/binding-linux-riscv64-gnu",
        "node_modules/@oxlint/binding-linux-riscv64-musl",
        "node_modules/@oxlint/binding-linux-s390x-gnu",
        "node_modules/@oxlint/binding-linux-x64-gnu",
        "node_modules/@oxlint/binding-linux-x64-musl",
        "node_modules/@oxlint/binding-openharmony-arm64",
        "node_modules/@oxlint/binding-win32-arm64-msvc",
        "node_modules/@oxlint/binding-win32-ia32-msvc",
        "node_modules/@oxlint/binding-win32-x64-msvc",
        "node_modules/@redocly/ajv",
        "node_modules/@redocly/config",
        "node_modules/@redocly/openapi-core",
        "node_modules/@redocly/openapi-core/node_modules/minimatch",
        "node_modules/@rolldown/binding-android-arm64",
        "node_modules/@rolldown/binding-darwin-arm64",
        "node_modules/@rolldown/binding-darwin-x64",
        "node_modules/@rolldown/binding-freebsd-x64",
        "node_modules/@rolldown/binding-linux-arm-gnueabihf",
        "node_modules/@rolldown/binding-linux-arm64-gnu",
        "node_modules/@rolldown/binding-linux-arm64-musl",
        "node_modules/@rolldown/binding-linux-ppc64-gnu",
        "node_modules/@rolldown/binding-linux-s390x-gnu",
        "node_modules/@rolldown/binding-linux-x64-gnu",
        "node_modules/@rolldown/binding-linux-x64-musl",
        "node_modules/@rolldown/binding-openharmony-arm64",
        "node_modules/@rolldown/binding-win32-arm64-msvc",
        "node_modules/@rolldown/binding-win32-x64-msvc",
        "node_modules/@rolldown/pluginutils",
        "node_modules/@standard-schema/spec",
        "node_modules/@tailwindcss/node",
        "node_modules/@tailwindcss/oxide",
        "node_modules/@tailwindcss/oxide-android-arm64",
        "node_modules/@tailwindcss/oxide-darwin-arm64",
        "node_modules/@tailwindcss/oxide-darwin-x64",
        "node_modules/@tailwindcss/oxide-freebsd-x64",
        "node_modules/@tailwindcss/oxide-linux-arm-gnueabihf",
        "node_modules/@tailwindcss/oxide-linux-arm64-gnu",
        "node_modules/@tailwindcss/oxide-linux-arm64-musl",
        "node_modules/@tailwindcss/oxide-linux-x64-gnu",
        "node_modules/@tailwindcss/oxide-linux-x64-musl",
        "node_modules/@tailwindcss/oxide-wasm32-wasi",
        "node_modules/@tailwindcss/oxide-wasm32-wasi/node_modules/@emnapi/core",
        "node_modules/@tailwindcss/oxide-wasm32-wasi/node_modules/@emnapi/runtime",
        "node_modules/@tailwindcss/oxide-wasm32-wasi/node_modules/@emnapi/wasi-threads",
        "node_modules/@tailwindcss/oxide-wasm32-wasi/node_modules/@napi-rs/wasm-runtime",
        "node_modules/@tailwindcss/oxide-wasm32-wasi/node_modules/@tybys/wasm-util",
        "node_modules/@tailwindcss/oxide-wasm32-wasi/node_modules/tslib",
        "node_modules/@tailwindcss/oxide-win32-arm64-msvc",
        "node_modules/@tailwindcss/oxide-win32-x64-msvc",
        "node_modules/@tailwindcss/vite",
        "node_modules/@tanstack/query-core",
        "node_modules/@tanstack/react-query",
        "node_modules/@testing-library/dom",
        "node_modules/@testing-library/jest-dom",
        "node_modules/@testing-library/jest-dom/node_modules/dom-accessibility-api",
        "node_modules/@testing-library/react",
        "node_modules/@testing-library/user-event",
        "node_modules/@types/aria-query",
        "node_modules/@types/chai",
        "node_modules/@types/deep-eql",
        "node_modules/@types/estree",
        "node_modules/@types/node",
        "node_modules/@types/react",
        "node_modules/@types/react-dom",
        "node_modules/@vitejs/plugin-react",
        "node_modules/@vitest/expect",
        "node_modules/@vitest/mocker",
        "node_modules/@vitest/pretty-format",
        "node_modules/@vitest/runner",
        "node_modules/@vitest/snapshot",
        "node_modules/@vitest/spy",
        "node_modules/@vitest/utils",
        "node_modules/agent-base",
        "node_modules/ansi-colors",
        "node_modules/ansi-regex",
        "node_modules/ansi-styles",
        "node_modules/argparse",
        "node_modules/aria-query",
        "node_modules/assertion-error",
        "node_modules/balanced-match",
        "node_modules/brace-expansion",
        "node_modules/chai",
        "node_modules/change-case",
        "node_modules/class-variance-authority",
        "node_modules/clsx",
        "node_modules/colorette",
        "node_modules/convert-source-map",
        "node_modules/cookie",
        "node_modules/css.escape",
        "node_modules/cssstyle",
        "node_modules/csstype",
        "node_modules/data-urls",
        "node_modules/debug",
        "node_modules/decimal.js",
        "node_modules/dequal",
        "node_modules/detect-libc",
        "node_modules/dom-accessibility-api",
        "node_modules/enhanced-resolve",
        "node_modules/entities",
        "node_modules/es-module-lexer",
        "node_modules/esbuild",
        "node_modules/estree-walker",
        "node_modules/expect-type",
        "node_modules/fancy-canvas",
        "node_modules/fast-deep-equal",
        "node_modules/fdir",
        "node_modules/fsevents",
        "node_modules/graceful-fs",
        "node_modules/html-encoding-sniffer",
        "node_modules/http-proxy-agent",
        "node_modules/https-proxy-agent",
        "node_modules/indent-string",
        "node_modules/index-to-position",
        "node_modules/is-potential-custom-element-name",
        "node_modules/jiti",
        "node_modules/js-levenshtein",
        "node_modules/js-tokens",
        "node_modules/js-yaml",
        "node_modules/jsdom",
        "node_modules/json-schema-traverse",
        "node_modules/lightningcss",
        "node_modules/lightningcss-android-arm64",
        "node_modules/lightningcss-darwin-arm64",
        "node_modules/lightningcss-darwin-x64",
        "node_modules/lightningcss-freebsd-x64",
        "node_modules/lightningcss-linux-arm-gnueabihf",
        "node_modules/lightningcss-linux-arm64-gnu",
        "node_modules/lightningcss-linux-arm64-musl",
        "node_modules/lightningcss-linux-x64-gnu",
        "node_modules/lightningcss-linux-x64-musl",
        "node_modules/lightningcss-win32-arm64-msvc",
        "node_modules/lightningcss-win32-x64-msvc",
        "node_modules/lightweight-charts",
        "node_modules/lucide-react",
        "node_modules/lz-string",
        "node_modules/magic-string",
        "node_modules/min-indent",
        "node_modules/ms",
        "node_modules/nanoid",
        "node_modules/nwsapi",
        "node_modules/obug",
        "node_modules/openapi-fetch",
        "node_modules/openapi-typescript",
        "node_modules/openapi-typescript-helpers",
        "node_modules/openapi-typescript/node_modules/parse-json",
        "node_modules/oxlint",
        "node_modules/parse5",
        "node_modules/pathe",
        "node_modules/picocolors",
        "node_modules/picomatch",
        "node_modules/pluralize",
        "node_modules/postcss",
        "node_modules/pretty-format",
        "node_modules/punycode",
        "node_modules/react",
        "node_modules/react-dom",
        "node_modules/react-is",
        "node_modules/react-router",
        "node_modules/react-router-dom",
        "node_modules/redent",
        "node_modules/require-from-string",
        "node_modules/reselect",
        "node_modules/rolldown",
        "node_modules/rrweb-cssom",
        "node_modules/safer-buffer",
        "node_modules/saxes",
        "node_modules/scheduler",
        "node_modules/set-cookie-parser",
        "node_modules/siginfo",
        "node_modules/source-map-js",
        "node_modules/stackback",
        "node_modules/std-env",
        "node_modules/strip-indent",
        "node_modules/supports-color",
        "node_modules/symbol-tree",
        "node_modules/tailwind-merge",
        "node_modules/tailwindcss",
        "node_modules/tapable",
        "node_modules/tinybench",
        "node_modules/tinyexec",
        "node_modules/tinyglobby",
        "node_modules/tinyrainbow",
        "node_modules/tldts",
        "node_modules/tldts-core",
        "node_modules/tough-cookie",
        "node_modules/tr46",
        "node_modules/tw-animate-css",
        "node_modules/type-fest",
        "node_modules/typescript",
        "node_modules/undici-types",
        "node_modules/uri-js-replace",
        "node_modules/use-sync-external-store",
        "node_modules/vite",
        "node_modules/vite/node_modules/lightningcss",
        "node_modules/vite/node_modules/lightningcss-android-arm64",
        "node_modules/vite/node_modules/lightningcss-darwin-arm64",
        "node_modules/vite/node_modules/lightningcss-darwin-x64",
        "node_modules/vite/node_modules/lightningcss-freebsd-x64",
        "node_modules/vite/node_modules/lightningcss-linux-arm-gnueabihf",
        "node_modules/vite/node_modules/lightningcss-linux-arm64-gnu",
        "node_modules/vite/node_modules/lightningcss-linux-arm64-musl",
        "node_modules/vite/node_modules/lightningcss-linux-x64-gnu",
        "node_modules/vite/node_modules/lightningcss-linux-x64-musl",
        "node_modules/vite/node_modules/lightningcss-win32-arm64-msvc",
        "node_modules/vite/node_modules/lightningcss-win32-x64-msvc",
        "node_modules/vitest",
        "node_modules/w3c-xmlserializer",
        "node_modules/webidl-conversions",
        "node_modules/whatwg-encoding",
        "node_modules/whatwg-encoding/node_modules/iconv-lite",
        "node_modules/whatwg-mimetype",
        "node_modules/whatwg-url",
        "node_modules/why-is-node-running",
        "node_modules/ws",
        "node_modules/xml-name-validator",
        "node_modules/xmlchars",
        "node_modules/yaml-ast-parser",
        "node_modules/yargs-parser",
    }
)

PARENT = "node_modules/bundled-parent"
CHILD = PARENT + "/node_modules/child"
OTHER = PARENT + "/node_modules/@scope/other"


def _sri(raw: bytes) -> str:
    return "sha512-" + base64.b64encode(hashlib.sha512(raw).digest()).decode()


def _tar(entries: list[tuple[str, bytes, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, body, kind in entries:
            member = tarfile.TarInfo(name)
            member.type = kind
            member.size = len(body) if kind == tarfile.REGTYPE else 0
            if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                member.linkname = "/outside"
            archive.addfile(member, io.BytesIO(body) if member.isfile() else None)
    return gzip.compress(buffer.getvalue(), mtime=0)


def _fixture():
    outer = {
        "name": "bundled-parent",
        "version": "1.0.0",
        "bundleDependencies": ["child", "@scope/other"],
        "license": "MIT",
    }
    entries = [
        ("package/package.json", json.dumps(outer).encode(), tarfile.REGTYPE),
        (
            "package/node_modules/child/package.json",
            b'{"name":"child","version":"1.0.1","license":"MIT"}',
            tarfile.REGTYPE,
        ),
        ("package/node_modules/child/index.js", b"export const value = 7", tarfile.REGTYPE),
        (
            "package/node_modules/@scope/other/package.json",
            b'{"name":"@scope/other","version":"2.0.0","license":"0BSD"}',
            tarfile.REGTYPE,
        ),
        ("package/node_modules/@scope/other/LICENSE.txt", b"0BSD notice", tarfile.REGTYPE),
    ]
    raw = _tar(entries)
    document = {
        "lockfileVersion": 3,
        "packages": {
            "": {},
            PARENT: {
                "version": "1.0.0",
                "license": "MIT",
                "resolved": "https://registry.npmjs.org/bundled-parent/-/bundled-parent-1.0.0.tgz",
                "integrity": _sri(raw),
                "bundleDependencies": ["child", "@scope/other"],
            },
            CHILD: {"version": "1.0.1", "license": "MIT", "inBundle": True},
            OTHER: {"version": "2.0.0", "license": "0BSD", "inBundle": True},
        },
    }
    return document, raw, entries


def test_bundle_proof_counts_every_child_and_hashes_actual_contents():
    review = _review_module()
    document, raw, _ = _fixture()
    inventory = review.review_lock_document(document, bundle_archives={PARENT: raw})
    assert set(inventory) == {PARENT, CHILD, OTHER}
    assert inventory[OTHER]["license"] == "0BSD"
    proof = inventory[CHILD]["bundle"]
    assert proof["parent"] == PARENT
    assert proof["parent_integrity"] == _sri(raw)
    assert {row["path"] for row in proof["files"]} == {"package.json", "index.js"}
    code = next(row for row in proof["files"] if row["path"] == "index.js")
    assert code["sha256"] == hashlib.sha256(b"export const value = 7").hexdigest()
    assert proof["notice_qualification"] == "NOT_QUALIFIED_FOR_FULL_NOTICE_REDISTRIBUTION"


@pytest.mark.parametrize(
    "case",
    [
        "missing_proof",
        "boolean_receipt",
        "wrong_sri",
        "untrusted_parent",
        "invalid_parent_url",
        "unhashable_parent_license",
        "missing_parent",
        "invented_parent",
        "missing_declaration",
        "missing_child",
        "missing_all_children",
        "extra_proof",
        "wrong_version",
        "wrong_license",
        "unallowed_license",
        "fake_child_registry",
        "false_bundle_flag",
        "nonboolean_bundle_flag",
        "nested_bundle",
        "second_parent",
    ],
)
def test_bundle_lock_and_proof_refusals(case):
    review = _review_module()
    document, raw, _ = _fixture()
    packages = document["packages"]
    archives = {PARENT: raw}
    if case == "missing_proof":
        archives = {}
    elif case == "boolean_receipt":
        archives = {PARENT: True}
    elif case == "wrong_sri":
        packages[PARENT]["integrity"] = "sha512-wrong"
    elif case == "untrusted_parent":
        packages[PARENT]["resolved"] = "https://example.invalid/a.tgz"
    elif case == "invalid_parent_url":
        packages[PARENT]["resolved"] = "https://[invalid"
    elif case == "unhashable_parent_license":
        packages[PARENT]["license"] = ["MIT"]
    elif case == "missing_parent":
        del packages[PARENT]
    elif case == "invented_parent":
        packages[PARENT]["version"] = "9.0.0"
    elif case == "missing_declaration":
        packages[PARENT]["bundleDependencies"] = ["child"]
    elif case == "missing_child":
        del packages[OTHER]
    elif case == "missing_all_children":
        del packages[CHILD]
        del packages[OTHER]
    elif case == "extra_proof":
        archives["node_modules/not-parent"] = raw
    elif case == "wrong_version":
        packages[CHILD]["version"] = "9.0.0"
    elif case == "wrong_license":
        packages[CHILD]["license"] = "ISC"
    elif case == "unallowed_license":
        packages[CHILD]["license"] = "GPL-3.0-only"
    elif case == "fake_child_registry":
        packages[CHILD]["resolved"] = packages[PARENT]["resolved"]
    elif case == "false_bundle_flag":
        packages[CHILD]["inBundle"] = False
    elif case == "nonboolean_bundle_flag":
        packages[CHILD]["inBundle"] = 1
    elif case == "nested_bundle":
        packages[CHILD]["bundleDependencies"] = ["deep"]
        packages[CHILD + "/node_modules/deep"] = {
            "version": "1.0.0",
            "license": "MIT",
            "inBundle": True,
        }
    elif case == "second_parent":
        packages["node_modules/another"] = copy.deepcopy(packages[PARENT])
        packages["node_modules/another/node_modules/child"] = copy.deepcopy(packages[CHILD])
    with pytest.raises(review.FrontendLicenseError):
        review.review_lock_document(document, bundle_archives=archives)


@pytest.mark.parametrize(
    "name,kind",
    [
        ("package/../escape", tarfile.REGTYPE),
        ("/absolute", tarfile.REGTYPE),
        ("package/a\\b", tarfile.REGTYPE),
        ("package/a:b", tarfile.REGTYPE),
        ("package/a.", tarfile.REGTYPE),
        ("package/CON.txt", tarfile.REGTYPE),
        ("package/link", tarfile.SYMTYPE),
        ("package/hard", tarfile.LNKTYPE),
        ("package/pipe", tarfile.FIFOTYPE),
        ("package/node_modules/child/index.js", tarfile.REGTYPE),
        ("package/node_modules/stranger/package.json", tarfile.REGTYPE),
        ("package/node_modules/unlisted/index.js", tarfile.REGTYPE),
        ("package/node_modules/child/node_modules/deep/index.js", tarfile.REGTYPE),
    ],
)
def test_bundle_archive_paths_types_and_extra_members_fail_closed(name, kind):
    review = _review_module()
    document, _, entries = _fixture()
    raw = _tar(entries + [(name, b"{}", kind)])
    document["packages"][PARENT]["integrity"] = _sri(raw)
    with pytest.raises(review.FrontendLicenseError):
        review.review_lock_document(document, bundle_archives={PARENT: raw})


@pytest.mark.parametrize(
    "extra",
    [
        [("package/A.js", b"a", tarfile.REGTYPE), ("package/a.js", b"b", tarfile.REGTYPE)],
        [("package/file", b"x", tarfile.REGTYPE), ("package/file/child", b"y", tarfile.REGTYPE)],
    ],
)
def test_bundle_archive_aliases_fail_closed(extra):
    review = _review_module()
    document, _, entries = _fixture()
    raw = _tar(entries + extra)
    document["packages"][PARENT]["integrity"] = _sri(raw)
    with pytest.raises(review.FrontendLicenseError):
        review.review_lock_document(document, bundle_archives={PARENT: raw})


@pytest.mark.parametrize(
    "case",
    [
        "parent_identity",
        "child_identity",
        "duplicate_json",
        "missing_manifest",
        "parent_license",
        "child_license_array",
        "conflicting_parent_alias",
        "actual_nested_bundle",
    ],
)
def test_bundle_actual_manifest_refusals(case):
    review = _review_module()
    document, _, entries = _fixture()
    if case == "parent_identity":
        entries[0] = (entries[0][0], b'{"name":"invented","version":"1.0.0"}', tarfile.REGTYPE)
    elif case == "child_identity":
        entries[1] = (
            entries[1][0],
            b'{"name":"other","version":"1.0.1","license":"MIT"}',
            tarfile.REGTYPE,
        )
    elif case == "duplicate_json":
        entries[1] = (
            entries[1][0],
            b'{"name":"child","name":"child","version":"1.0.1","license":"MIT"}',
            tarfile.REGTYPE,
        )
    elif case == "parent_license":
        outer = json.loads(entries[0][1])
        outer["license"] = "ISC"
        entries[0] = (entries[0][0], json.dumps(outer).encode(), tarfile.REGTYPE)
    elif case == "child_license_array":
        child = json.loads(entries[1][1])
        child["license"] = ["MIT"]
        entries[1] = (entries[1][0], json.dumps(child).encode(), tarfile.REGTYPE)
    elif case == "conflicting_parent_alias":
        outer = json.loads(entries[0][1])
        outer["bundledDependencies"] = ["not-the-declared-members"]
        entries[0] = (entries[0][0], json.dumps(outer).encode(), tarfile.REGTYPE)
    elif case == "actual_nested_bundle":
        child = json.loads(entries[1][1])
        child["bundleDependencies"] = ["deep"]
        entries[1] = (entries[1][0], json.dumps(child).encode(), tarfile.REGTYPE)
    else:
        entries.pop(1)
    raw = _tar(entries)
    document["packages"][PARENT]["integrity"] = _sri(raw)
    with pytest.raises(review.FrontendLicenseError):
        review.review_lock_document(document, bundle_archives={PARENT: raw})


@pytest.mark.parametrize("limit", ["MAX_COMPRESSED", "MAX_EXPANDED", "MAX_MEMBERS"])
def test_bundle_archive_resource_caps(monkeypatch, limit):
    review = _review_module()
    document, raw, _ = _fixture()
    monkeypatch.setattr(review, limit, 1)
    with pytest.raises(review.FrontendLicenseError):
        review.review_lock_document(document, bundle_archives={PARENT: raw})


def test_bundle_corruption_is_not_relabelled_as_metadata(monkeypatch):
    review = _review_module()
    document, raw, _ = _fixture()
    with pytest.raises(review.FrontendLicenseError):
        review.review_lock_document(document, bundle_archives={PARENT: raw[:-1]})
    document["packages"][PARENT]["integrity"] = _sri(b"not gzip")
    with pytest.raises(review.FrontendLicenseError):
        review.review_lock_document(document, bundle_archives={PARENT: b"not gzip"})


def test_bundle_cache_rechecks_bytes_and_never_trusts_receipts(tmp_path, monkeypatch):
    review = _review_module()
    document, raw, _ = _fixture()
    fetched = []

    def download(url):
        fetched.append(url)
        return raw

    monkeypatch.setattr(review, "_download_archive", download)
    first = review.load_bundle_archives(document, cache_dir=tmp_path)
    assert first == {PARENT: raw}
    assert fetched == [document["packages"][PARENT]["resolved"]]
    assert review.load_bundle_archives(document, cache_dir=tmp_path) == first
    assert len(fetched) == 1
    cache = next(tmp_path.glob("*.tgz"))
    cache.write_bytes(b"tampered")
    with pytest.raises(review.FrontendLicenseError):
        review.load_bundle_archives(document, cache_dir=tmp_path)
    assert len(fetched) == 1


def test_no_bundle_never_fetches_artifacts(monkeypatch, tmp_path):
    review = _review_module()

    def unexpected(url):
        raise AssertionError("no bundle must not access network")

    monkeypatch.setattr(review, "_download_archive", unexpected)
    assert (
        review.load_bundle_archives(
            {"lockfileVersion": 3, "packages": {"": {}}}, cache_dir=tmp_path
        )
        == {}
    )
    assert list(tmp_path.iterdir()) == []


def test_bundle_redirects_are_refused():
    review = _review_module()
    with pytest.raises(review.FrontendLicenseError):
        review._RejectRedirect().redirect_request(
            None, None, 302, "", {}, "https://example.invalid/x"
        )


def test_bundle_declaration_order_is_not_identity():
    review = _review_module()
    document, raw, _ = _fixture()
    document["packages"][PARENT]["bundleDependencies"].reverse()
    inventory = review.review_lock_document(document, bundle_archives={PARENT: raw})
    assert set(inventory) == {PARENT, CHILD, OTHER}


def test_bundle_trailing_unparsed_content_is_refused():
    review = _review_module()
    document, raw, _ = _fixture()
    raw = gzip.compress(gzip.decompress(raw) + b"unparsed second payload", mtime=0)
    document["packages"][PARENT]["integrity"] = _sri(raw)
    with pytest.raises(review.FrontendLicenseError):
        review.review_lock_document(document, bundle_archives={PARENT: raw})


def test_bundle_download_body_deadline_is_enforced(monkeypatch):
    review = _review_module()
    url = "https://registry.npmjs.org/bundled-parent/-/bundled-parent-1.0.0.tgz"

    class Response:
        def geturl(self):
            return url

        def read(self, _amount):
            return b"x"

        def read1(self, _amount):
            return b"x"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    class Opener:
        def open(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(review.urllib.request, "build_opener", lambda *_args: Opener())
    ticks = iter([0, 31])
    monkeypatch.setattr(review, "_monotonic", lambda: next(ticks), raising=False)
    with pytest.raises(review.FrontendLicenseError, match="deadline"):
        review._download_archive(url)


@pytest.mark.parametrize("receipt", [False, True])
def test_boolean_receipt_is_not_an_archive_mapping_even_without_bundles(receipt):
    review = _review_module()
    document = {
        "lockfileVersion": 3,
        "packages": {
            "": {},
            "node_modules/plain": {
                "version": "1.0.0",
                "license": "MIT",
                "resolved": "https://registry.npmjs.org/plain/-/plain-1.0.0.tgz",
                "integrity": "sha512-test",
            },
        },
    }
    with pytest.raises(review.FrontendLicenseError):
        review.review_lock_document(document, bundle_archives=receipt)
