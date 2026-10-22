"use strict";

const { createRequire } = require("node:module");
const { isAbsolute, relative, resolve, sep } = require("node:path");
const { existsSync, readFileSync } = require("node:fs");

const frontend = process.cwd();
const runnerHeader = process.report.getReport().header;
const glibc = runnerHeader.glibcVersionRuntime || null;
const libc = process.platform === "linux" ? (glibc ? "gnu" : "musl-or-unreported") : null;
const nativeSuffix = process.platform === "linux" ? `-${libc === "gnu" ? "gnu" : "musl"}` : "";
const nativeName = `lightningcss-${process.platform}-${process.arch}${nativeSuffix}`;

function safePath(path) {
  const value = relative(frontend, resolve(path)).split(sep).join("/");
  return value && value !== ".." && !value.startsWith("../") && !isAbsolute(value)
    ? value
    : "<outside-frontend>";
}

function safeError(error) {
  const rawCode = error && typeof error.code === "string" ? error.code : "UNKNOWN";
  let message = String(error && error.message ? error.message : error);
  message = message
    .replace(/((?:token|password|secret|credential|dsn)\s*[:=]\s*)[^\s,;]+/gi, "$1<redacted>")
    .replace(/(^|[\s("'`])\/(?:[^\s"'`<>]+\/?)+/g, "$1<absolute-path>")
    .replace(/\b[A-Za-z]:\\[^\s"'`<>]+/g, "<absolute-path>")
    .slice(0, 360);
  return {
    code: /^[A-Z0-9_]+$/.test(rawCode) ? rawCode : "UNKNOWN",
    message,
  };
}

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function findPackageRoot(entry) {
  let current = resolve(entry);
  while (current !== resolve(frontend, "..")) {
    if (existsSync(resolve(current, "package.json"))) return current;
    const parent = resolve(current, "..");
    if (parent === current) break;
    current = parent;
  }
  return null;
}

function lockRecord(lock, packagePath) {
  const item = lock.packages && lock.packages[packagePath];
  if (!item) return { present: false };
  return {
    present: true,
    version: typeof item.version === "string" ? item.version : null,
    optional: item.optional === true,
    os: Array.isArray(item.os) ? item.os : [],
    cpu: Array.isArray(item.cpu) ? item.cpu : [],
    integrityPresent: typeof item.integrity === "string" && item.integrity.length > 0,
  };
}

function attempt(context, contextManifest, cssLockPath, nativeLockPath, lock) {
  const result = { context, installed: false };
  try {
    const ownerRequire = createRequire(resolve(frontend, contextManifest));
    const cssEntry = ownerRequire.resolve("lightningcss");
    const cssRoot = findPackageRoot(cssEntry);
    const cssManifest = cssRoot ? readJson(resolve(cssRoot, "package.json")) : null;
    const cssRequire = createRequire(cssEntry);
    result.css = {
      entry: safePath(cssEntry),
      installedVersion: cssManifest && typeof cssManifest.version === "string" ? cssManifest.version : null,
      locked: lockRecord(lock, cssLockPath),
      load: "PASS",
    };
    result.installed = true;

    try {
      const nativeEntry = cssRequire.resolve(nativeName);
      const nativeRoot = findPackageRoot(nativeEntry);
      const nativeManifest = nativeRoot ? readJson(resolve(nativeRoot, "package.json")) : null;
      const nativeApi = cssRequire(nativeName);
      result.native = {
        name: nativeName,
        entry: safePath(nativeEntry),
        packageManifestPresent: Boolean(nativeManifest),
        installedVersion: nativeManifest && typeof nativeManifest.version === "string" ? nativeManifest.version : null,
        locked: lockRecord(lock, nativeLockPath),
        load: "PASS",
        transformType: typeof nativeApi.transform,
      };
    } catch (error) {
      result.native = {
        name: nativeName,
        packageManifestPresent: existsSync(resolve(frontend, nativeLockPath, "package.json")),
        locked: lockRecord(lock, nativeLockPath),
        load: "FAIL",
        error: safeError(error),
      };
      process.exitCode = 1;
    }

    try {
      const cssApi = cssRequire("lightningcss");
      result.css.apiLoad = "PASS";
      result.css.transformType = typeof cssApi.transform;
    } catch (error) {
      result.css.apiLoad = "FAIL";
      result.css.error = safeError(error);
      process.exitCode = 1;
    }
  } catch (error) {
    result.load = "FAIL";
    result.error = safeError(error);
    process.exitCode = 1;
  }
  return result;
}

function main() {
  const lock = readJson(resolve(frontend, "package-lock.json"));
  const npmCiExit = process.env.NATIVE_CSS_NPM_CI_EXIT;
  const npmVersion = process.env.NATIVE_CSS_NPM_VERSION;
  const npmStatus = /^\d+$/.test(npmCiExit || "") ? Number(npmCiExit) : null;
  const contexts = [
    {
      context: "frontend-root",
      manifest: "package.json",
      cssLock: "node_modules/lightningcss",
      nativeLock: `node_modules/${nativeName}`,
    },
    {
      context: "vite-resolution",
      manifest: "node_modules/vite/package.json",
      cssLock: "node_modules/vite/node_modules/lightningcss",
      nativeLock: `node_modules/vite/node_modules/${nativeName}`,
    },
  ];
  const report = {
    schemaVersion: 1,
    node: process.version,
    npm: typeof npmVersion === "string" && /^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$/.test(npmVersion)
      ? npmVersion
      : "unavailable",
    platform: process.platform,
    arch: process.arch,
    libc,
    glibcVersionRuntime: glibc,
    npmCiExit: npmStatus,
    lockfileVersion: lock.lockfileVersion,
    expectedNativePackage: nativeName,
    attempts: contexts.map((item) =>
      attempt(item.context, item.manifest, item.cssLock, item.nativeLock, lock),
    ),
  };
  if (npmStatus !== 0) process.exitCode = 1;
  process.stdout.write(`${JSON.stringify(report)}\n`);
}

try {
  main();
} catch (error) {
  process.exitCode = 1;
  process.stdout.write(`${JSON.stringify({ schemaVersion: 1, status: "probe-error", error: safeError(error) })}\n`);
}
