#!/usr/bin/env python3

import argparse
import os
import stat
import subprocess
from pathlib import Path


def run(cmd, *, capture_output=False, check=True):
    return subprocess.run(
        cmd,
        text=True,
        capture_output=capture_output,
        check=check,
    )


def build_installer(*, flake: str, attribute: str, out_link: str | None):
    cmd = ["nix", "build", f"{flake}#{attribute}", "--print-out-paths"]
    if out_link is None:
        cmd.append("--no-link")
    else:
        cmd.extend(["--out-link", out_link])

    result = run(cmd, capture_output=True)
    return Path(result.stdout.strip().splitlines()[-1]).resolve()


def locate_image_file(image_output: Path):
    candidates = sorted(image_output.rglob("*.iso"))
    if candidates == []:
        candidates = sorted(image_output.rglob("*.img"))
    if candidates == []:
        raise SystemExit(f"Could not find an .iso or .img under build output '{image_output}'.")
    return candidates[0]


def ensure_block_device(device: str):
    try:
        device_stat = os.stat(device)
    except FileNotFoundError as exc:
        raise SystemExit(f"Device '{device}' does not exist.") from exc

    if not stat.S_ISBLK(device_stat.st_mode):
        raise SystemExit(f"Device '{device}' is not a block device.")


def handle_build(args):
    image_output = build_installer(
        flake=args.flake,
        attribute=args.attribute,
        out_link=None if args.no_link else args.out_link,
    )
    image_file = locate_image_file(image_output)

    if args.print_image_path:
        print(image_file)
        return

    print(f"Build output: {image_output}")
    print(f"Image file: {image_file}")


def handle_write(args):
    ensure_block_device(args.device)

    image_file = (
        Path(args.image).expanduser().resolve()
        if args.image is not None
        else locate_image_file(
            build_installer(
                flake=args.flake,
                attribute=args.attribute,
                out_link=args.out_link,
            )
        )
    )

    run(
        [
            "dd",
            f"if={image_file}",
            f"of={args.device}",
            "bs=16M",
            "conv=fsync",
            "oflag=direct",
            "status=progress",
        ]
    )
    run(["sync"])

    print(f"Wrote {image_file} to {args.device}")


def main():
    parser = argparse.ArgumentParser(
        description="Build or write the SSH-enabled live installer image."
    )
    parser.add_argument(
        "mode",
        nargs="?",
        default="build",
        choices=["build", "write"],
        help="Whether to build the image or write it to a device",
    )
    parser.add_argument("--flake", default=".", help="Flake reference to build from")
    parser.add_argument("--attribute", default="live-installer-iso", help="Flake package attribute for the installer image")
    parser.add_argument("--out-link", default="result-live-installer", help="Symlink path to create for the build result")
    parser.add_argument("--no-link", action="store_true", help="Do not create an output symlink")
    parser.add_argument("--print-image-path", action="store_true", help="Print only the resolved image file path after building")
    parser.add_argument("--device", help="Block device to overwrite, such as /dev/sdX")
    parser.add_argument("--image", help="Prebuilt .iso or .img path. If omitted during write, the installer is built first.")
    args = parser.parse_args()

    if args.mode == "write":
        if args.device is None:
            raise SystemExit("--device is required when mode is 'write'.")
        handle_write(args)
        return

    handle_build(args)


if __name__ == "__main__":
    main()
