#!/usr/bin/env python3
import argparse
import re
import shutil
import subprocess
import sys

DEFAULT_DEVICE = "/dev/video0"
DEFAULT_FPS = 30
FORMAT_NAME_MAP = {
    "MJPG": "mjpeg",
    "YUYV": "yuyv",
    "YUY2": "yuyv",
}

PIPELINE_TEMPLATE = {
    "mjpeg": (
        "v4l2src device={device} io-mode={io_mode} do-timestamp=true ! "
        "image/jpeg,width={width},height={height},framerate={fps}/1 ! "
        "jpegdec ! videoconvert ! queue max-size-buffers=1 leaky=downstream ! "
        "autovideosink sync=false"
    ),
    "yuyv": (
        "v4l2src device={device} io-mode={io_mode} do-timestamp=true ! "
        "video/x-raw,format=YUY2,width={width},height={height},framerate={fps}/1 ! "
        "queue max-size-buffers=1 leaky=downstream ! videoconvert ! "
        "autovideosink sync=false"
    ),
}


def check_tool(name):
    if shutil.which(name) is None:
        print(f"Error: required tool '{name}' not found in PATH.", file=sys.stderr)
        sys.exit(1)


def build_pipeline(device, width, height, fps, fmt, io_mode):
    template = PIPELINE_TEMPLATE.get(fmt)
    if template is None:
        raise ValueError(f"Unsupported format: {fmt}")
    return template.format(
        device=device,
        width=width,
        height=height,
        fps=fps,
        io_mode=io_mode,
    )


def get_supported_modes(device):
    proc = subprocess.run(
        ["v4l2-ctl", "-d", device, "--list-formats-ext"],
        text=True,
        capture_output=True,
        check=False,
    )
    output = proc.stdout or proc.stderr or ""

    modes = {}
    current_format = None
    current_size = None

    for line in output.splitlines():
        stripped = line.strip()
        fmt_match = re.match(r"\[\d+\]: '(.+?)'", stripped)
        if fmt_match:
            fourcc = fmt_match.group(1)
            current_format = FORMAT_NAME_MAP.get(fourcc)
            current_size = None
            if current_format:
                modes.setdefault(current_format, {})
            continue

        if current_format is None:
            continue

        size_match = re.search(r"Size: Discrete (\d+)x(\d+)", stripped)
        if size_match:
            current_size = (int(size_match.group(1)), int(size_match.group(2)))
            modes[current_format].setdefault(current_size, [])
            continue

        interval_match = re.search(r"Interval: Discrete ([0-9.]+)s", stripped)
        if interval_match and current_size is not None:
            interval = float(interval_match.group(1))
            fps = round(1.0 / interval)
            if fps not in modes[current_format][current_size]:
                modes[current_format][current_size].append(fps)

    return modes


def parse_v4l2_devices():
    proc = subprocess.run(
        ["v4l2-ctl", "--list-devices"],
        text=True,
        capture_output=True,
        check=False,
    )
    output = proc.stdout or proc.stderr or ""

    devices = {}
    current_name = None

    for line in output.splitlines():
        if not line.strip():
            current_name = None
            continue

        if line.startswith("\t") or line.startswith(" "):
            if current_name is not None:
                node = line.strip()
                devices.setdefault(current_name, []).append(node)
            continue

        current_name = line.strip()
        devices.setdefault(current_name, [])

    return devices


def score_device(device):
    modes = get_supported_modes(device)
    score = 0
    for fmt, sizes in modes.items():
        for (width, height), fps_list in sizes.items():
            highest_fps = max(fps_list) if fps_list else 0
            score = max(score, width * height * highest_fps)
    return score


def find_best_capture_device():
    devices = parse_v4l2_devices()
    best_device = None
    best_score = 0

    for label, nodes in devices.items():
        for node in nodes:
            if not node.startswith("/dev/video"):
                continue
            current_score = score_device(node)
            if current_score > best_score:
                best_score = current_score
                best_device = node

    if best_device is None:
        raise RuntimeError(
            "No usable video capture devices found. Use --list-devices to inspect devices."
        )

    return best_device


def list_devices():
    print("Available video devices:")
    subprocess.run(["v4l2-ctl", "--list-devices"], check=False)


def describe_device(device):
    print(f"Probing supported formats for {device}...")
    subprocess.run(["v4l2-ctl", "-d", device, "--list-formats-ext"], check=False)
    print(
        "\nPick the fastest supported format for your capture card (MJPG or YUYV/YUY2).\n"
    )


def validate_capture_settings(device, fmt, width, height, fps):
    modes = get_supported_modes(device)
    if fmt not in modes or not modes[fmt]:
        raise ValueError(
            f"Format '{fmt}' is not supported by {device}. Supported formats: {', '.join(modes)}"
        )

    size = (width, height)
    if size not in modes[fmt]:
        supported_sizes = sorted(modes[fmt].keys())
        raise ValueError(
            f"Resolution {width}x{height} is not supported for {fmt}. "
            f"Supported sizes: {', '.join(f'{w}x{h}' for w, h in supported_sizes)}"
        )

    supported_fps = sorted(modes[fmt][size])
    if fps not in supported_fps:
        raise ValueError(
            f"Framerate {fps} is not supported for {fmt} at {width}x{height}. "
            f"Supported FPS: {', '.join(str(v) for v in supported_fps)}"
        )


def run_gst(pipeline):
    command = ["gst-launch-1.0"] + pipeline.split()
    print("Running low-latency pipeline:")
    print(" ".join(command))
    subprocess.run(command)


def main():
    parser = argparse.ArgumentParser(
        description="Low-latency HDMI capture wrapper using GStreamer and v4l2."
    )
    parser.add_argument(
        "device",
        nargs="?",
        default=None,
        help="v4l2 device path (auto-detect if omitted)",
    )
    parser.add_argument("--width", type=int, default=1280, help="capture width")
    parser.add_argument("--height", type=int, default=720, help="capture height")
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS, help="capture framerate")
    parser.add_argument(
        "--format",
        choices=["mjpeg", "yuyv"],
        default="mjpeg",
        help="capture pixel format to use",
    )
    parser.add_argument(
        "--io-mode",
        type=int,
        choices=[0, 1, 2, 3, 4],
        default=4,
        help="v4l2src IO mode (0=auto, 1=read, 2=dmabuf, 3=mmap, 4=userptr)",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="print supported formats for the capture device and exit",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="list video devices and exit",
    )
    args = parser.parse_args()

    check_tool("gst-launch-1.0")
    check_tool("v4l2-ctl")

    if args.list_devices:
        list_devices()
        return

    device = args.device
    if device is None:
        device = find_best_capture_device()
        print(f"Auto-selected HDMI capture device: {device}")

    if args.probe:
        describe_device(device)
        return

    try:
        validate_capture_settings(
            device, args.format, args.width, args.height, args.fps
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        print(
            "Use --probe to inspect supported modes, then choose a matching width/height/fps."
        )
        sys.exit(1)

    pipeline = build_pipeline(
        device,
        args.width,
        args.height,
        args.fps,
        args.format,
        args.io_mode,
    )
    run_gst(pipeline)


if __name__ == "__main__":
    main()
