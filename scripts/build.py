#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build, sign, validate and package the standalone LSPosed module."""
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent.parent
NS = "{http://schemas.android.com/apk/res/android}"


def run(args, **kwargs):
    return subprocess.check_output([str(x) for x in args], **kwargs)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def archive(path, entries):
    with ZipFile(path, "w", compression=ZIP_DEFLATED, compresslevel=9) as output:
        for name, data in sorted(entries.items()):
            entry = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.compress_type = ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            output.writestr(entry, data)


def defined_classes(dex):
    def integer(offset):
        return struct.unpack_from("<I", dex, offset)[0]
    strings, types = integer(60), integer(68)
    count, definitions = integer(96), integer(100)
    names = []
    for i in range(count):
        string_index = integer(types + integer(definitions + i * 32) * 4)
        offset = integer(strings + string_index * 4)
        while dex[offset] & 0x80:
            offset += 1
        offset += 1
        names.append(dex[offset:dex.index(b"\x00", offset)].decode("utf-8"))
    return names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, default=Path(os.environ.get("ANDROID_SDK_ROOT") or
        os.environ.get("ANDROID_HOME") or str(Path.home() / ("AppData/Local/Android/Sdk" if os.name == "nt" else "Android/Sdk"))))
    parser.add_argument("--jdk", type=Path, default=Path(os.environ["JAVA_HOME"]) if os.environ.get("JAVA_HOME") else None)
    parser.add_argument("--build-tools", default="35.0.0")
    parser.add_argument("--build-dir", type=Path, default=Path(tempfile.gettempdir()) / "cloneprofile-build")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--xposed-api", type=Path)
    parser.add_argument("--keystore", type=Path, default=Path.home() / ".android/debug.keystore")
    parser.add_argument("--key-alias", default="androiddebugkey")
    args = parser.parse_args()
    manifest = ET.parse(ROOT / "AndroidManifest.xml").getroot()
    version = manifest.get(NS + "versionName")
    package = manifest.get("package")
    build_tools = args.sdk / "build-tools" / args.build_tools
    platform = args.sdk / "platforms/android-35/android.jar"
    suffix = ".exe" if os.name == "nt" else ""

    def java_tool(name):
        path = args.jdk / "bin" / (name + suffix) if args.jdk else Path(shutil.which(name) or "")
        if not path.is_file():
            raise RuntimeError("Set JAVA_HOME or pass --jdk for a JDK containing " + name)
        return path

    for path in [platform, build_tools / ("aapt" + suffix), build_tools / ("zipalign" + suffix),
                 build_tools / "lib/d8.jar", build_tools / "lib/apksigner.jar", args.keystore]:
        if not path.is_file():
            raise RuntimeError("Required build input is missing: " + str(path))
    args.build_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    dependency = json.loads((ROOT / "third_party/xposed-api/dependency.json").read_text(encoding="utf-8"))
    api = args.xposed_api or args.build_dir / "api-82.jar"
    if not api.is_file():
        if args.xposed_api:
            raise RuntimeError("The supplied Xposed API jar does not exist")
        contents = urllib.request.urlopen(dependency["url"], timeout=45).read()
        if hashlib.sha256(contents).hexdigest() != dependency["sha256"]:
            raise RuntimeError("Downloaded Xposed API hash does not match the pinned dependency")
        api.write_bytes(contents)
    if digest(api) != dependency["sha256"]:
        raise RuntimeError("Xposed API hash does not match the pinned dependency")

    with tempfile.TemporaryDirectory(prefix="compile-", dir=args.build_dir) as workspace:
        build = Path(workspace)
        classes, dex = build / "classes", build / "dex"
        classes.mkdir()
        dex.mkdir()
        sources = sorted((ROOT / "src").rglob("*.java"))
        run([java_tool("javac"), "--release", "8", "-encoding", "UTF-8", "-cp",
             os.pathsep.join([str(platform), str(api)]), "-d", classes, *sources])
        jar = build / "classes.jar"
        run([java_tool("jar"), "cf", jar, "-C", classes, "."])
        run([java_tool("java"), "-cp", build_tools / "lib/d8.jar", "com.android.tools.r8.D8",
             "--lib", platform, "--classpath", api, "--min-api", "28", "--output", dex, jar])
        base = build / "base.apk"
        run([build_tools / ("aapt" + suffix), "package", "-f", "-M", ROOT / "AndroidManifest.xml",
             "-S", ROOT / "res", "-I", platform, "-F", base])
        with ZipFile(base) as source:
            entries = {name: source.read(name) for name in source.namelist()}
        entries["classes.dex"] = (dex / "classes.dex").read_bytes()
        entries.update({"assets/" + path.relative_to(ROOT / "assets").as_posix(): path.read_bytes()
                        for path in (ROOT / "assets").rglob("*") if path.is_file()})
        entries.update({"META-INF/LICENSE": (ROOT / "LICENSE").read_bytes(),
                        "META-INF/NOTICE": (ROOT / "NOTICE").read_bytes()})
        # Android requires resources.arsc to be uncompressed for modern targets.
        normalized = build / "normalized.apk"
        with ZipFile(normalized, "w") as output:
            for name, contents in sorted(entries.items()):
                entry = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                entry.compress_type = 0 if name == "resources.arsc" else ZIP_DEFLATED
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                output.writestr(entry, contents)
        aligned = build / "aligned.apk"
        run([build_tools / ("zipalign" + suffix), "-f", "4", normalized, aligned])
        apk = args.output_dir / ("CloneProfileCompatibility-" + version + ".apk")
        environment = os.environ.copy()
        environment.setdefault("CLONEPROFILE_STORE_PASSWORD", "android")
        environment.setdefault("CLONEPROFILE_KEY_PASSWORD", "android")
        signer = [java_tool("java"), "-jar", build_tools / "lib/apksigner.jar"]
        run(signer + ["sign", "--ks", args.keystore, "--ks-key-alias", args.key_alias,
                      "--ks-pass", "env:CLONEPROFILE_STORE_PASSWORD", "--key-pass", "env:CLONEPROFILE_KEY_PASSWORD",
                      "--v4-signing-enabled", "false", "--out", apk, aligned], env=environment)
        signed = run(signer + ["verify", "--print-certs", apk]).decode("utf-8")
        certificate = re.search(r"certificate SHA-256 digest: ([0-9a-f]+)", signed).group(1)
        badging = run([build_tools / ("aapt" + suffix), "dump", "badging", apk]).decode("utf-8")
        if "name='" + package + "'" not in badging or "versionName='" + version + "'" not in badging:
            raise RuntimeError("APK package/version validation failed")
        classes = defined_classes(entries["classes.dex"])
        if not classes or any(not item.startswith("L" + package.replace(".", "/") + "/") for item in classes):
            raise RuntimeError("Unexpected classes were bundled into the APK")
        if entries["assets/xposed_init"].decode("utf-8").strip() != package + ".CloneCompat":
            raise RuntimeError("Unexpected LSPosed entry point")

    source_entries = {name: (ROOT / name).read_bytes() for name in
                      [".gitignore", ".gitattributes", "AndroidManifest.xml", "README.md", "LICENSE", "NOTICE", "build.ps1"]}
    for folder in ["src", "assets", "res", "scripts", "third_party", "licenses"]:
        for path in (ROOT / folder).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                source_entries[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    source_zip = args.output_dir / ("CloneProfileCompatibility-" + version + "-source.zip")
    prefix = "CloneProfileCompatibility-" + version + "/"
    archive(source_zip, {prefix + name: contents for name, contents in source_entries.items()})
    hashes = {path.name: digest(path) for path in [apk, source_zip]}
    (args.output_dir / "SHA256SUMS").write_text(
        "".join(value + "  " + name + "\n" for name, value in sorted(hashes.items())),
        encoding="utf-8", newline="\n")
    report = {"package": package, "version": version, "versionCode": int(manifest.get(NS + "versionCode")),
              "certificateSha256": certificate, "xposedApiSha256": dependency["sha256"],
              "definedClasses": classes, "artifacts": hashes}
    (args.output_dir / "validation.json").write_text(json.dumps(report, indent=2) + "\n",
                                                    encoding="utf-8", newline="\n")
    for name, value in hashes.items():
        print(value + "  " + name)


if __name__ == "__main__":
    main()
