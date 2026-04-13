#!/usr/bin/env python3
import argparse
import shutil
import subprocess
import sys

DEFAULT_DEVICE = "/dev/video2"

PIPELINE_TEMPLATE = {
    "mjpeg": (
        "v4l2src device={device} io-mode=4 do-timestamp=true ! "
        "image/jpeg,width={width},height={height},framerate={fps}/1 ! "
        "jpegdec ! videoconvert ! queue max-size-buffers=1 leaky=downstream ! "
        "autovideosink sync=false"
    ),
    "yuyv": (
        "v4l2src device={device} io-mode=4 do-timestamp=true ! "
        "video/x-raw,format=YUY2,width={width},height={height},framerate={fps}/1 ! "
        "queue max-size-buffers=1 leaky=downstream ! videoconvert ! "
        "autovideosink sync=false"
    ),
}


def check_tool(name):
    if shutil.which(name) is None:
        print(f"Error: required tool '{name}' not found in PATH.", file=sys.stderr)
        sys.exit(1)


def build_pipeline(device, width, height, fps, fmt):
    template = PIPELINE_TEMPLATE.get(fmt)
    if template is None:
        raise ValueError(f"Unsupported format: {fmt}")
    return template.format(device=device, width=width, height=height, fps=fps)


def describe_device(device):
    print(f"Probing supported formats for {device}...")
    subprocess.run(["v4l2-ctl", "-d", device, "--list-formats-ext"], check=False)
    print(
        "\nPick the fastest supported format for your capture card (MJPG or YUYV/YUY2).\n"
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
        "device", nargs="?", default=DEFAULT_DEVICE, help="v4l2 device path"
    )
    parser.add_argument("--width", type=int, default=1280, help="capture width")
    parser.add_argument("--height", type=int, default=720, help="capture height")
    parser.add_argument("--fps", type=int, default=60, help="capture framerate")
    parser.add_argument(
        "--format",
        choices=["mjpeg", "yuyv"],
        default="mjpeg",
        help="capture pixel format to use",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="print supported formats for the capture device before running",
    )
    args = parser.parse_args()

    check_tool("gst-launch-1.0")
    check_tool("v4l2-ctl")

    if args.probe:
        describe_device(args.device)

    pipeline = build_pipeline(
        args.device, args.width, args.height, args.fps, args.format
    )
    run_gst(pipeline)


if __name__ == "__main__":
    main()
