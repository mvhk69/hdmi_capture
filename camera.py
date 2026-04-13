import cv2
import threading
import time
from queue import Queue

# Global variables for threading and frame management
stop_event = threading.Event()  # Event to signal thread termination
frame_queue = Queue(maxsize=2)  # Queue to store the most recent frame (no frame drop)

# Capture settings
CAPTURE_WIDTH = 1366  # Desired frame width
CAPTURE_HEIGHT = 768  # Desired frame height
CAPTURE_FPS = 360  # Lowered FPS for better capture performance, adjust as needed


def initialize_capture_device(device_index):
    """
    Initialize the video capture device with the specified settings.

    Args:
        device_index (int): Index of the video capture device (e.g., 0 for default camera).

    Returns:
        cap (cv2.VideoCapture): Initialized video capture object.

    Raises:
        Exception: If the capture device cannot be opened.
    """
    cap = cv2.VideoCapture(
        device_index, cv2.CAP_DSHOW
    )  # Use DirectShow backend for Windows
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, CAPTURE_FPS)

    # Set MJPG codec to improve video quality
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

    # Verify if the capture device is opened successfully
    if not cap.isOpened():
        raise Exception(f"Failed to open capture device at index {device_index}.")

    # Validate the actual FPS
    actual_fps = cap.get(cv2.CAP_PROP_FPS)
    if actual_fps < CAPTURE_FPS:
        print(
            f"Warning: Requested FPS ({CAPTURE_FPS}) exceeds camera capability ({actual_fps})."
        )
    return cap


def capture_frames(cap):
    """
    Continuously capture frames from the video capture device in a separate thread.

    Args:
        cap (cv2.VideoCapture): Video capture object.
    """
    while not stop_event.is_set():
        ret, frame = cap.read()
        if ret:
            # Keep only the latest frame in the queue
            if not frame_queue.empty():
                frame_queue.get_nowait()
            frame_queue.put(frame)
        else:
            print("Warning: Failed to read frame from camera.")
        time.sleep(0.01)  # Small delay to reduce CPU usage


def show_camera(cap):
    """
    Display the video feed in a fullscreen OpenCV window.

    Args:
        cap (cv2.VideoCapture): Video capture object.
    """
    # Start the capture thread
    capture_thread = threading.Thread(target=capture_frames, args=(cap,), daemon=True)
    capture_thread.start()

    # Configure OpenCV window
    cv2.namedWindow("Video Capture", cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(
        "Video Capture", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN
    )

    while not stop_event.is_set():
        # Retrieve the latest frame from the queue
        if not frame_queue.empty():
            frame = frame_queue.get()
            cv2.imshow("Video Capture", frame)

        # Exit on 'q' key press
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            stop_event.set()

    # Wait for the capture thread to finish and release resources
    capture_thread.join()
    cap.release()
    cv2.destroyAllWindows()


def main():
    """
    Main function to initialize the video capture device and start the video feed.
    """
    device_index = 1  # Change to 0 if only one camera is available
    try:
        # Initialize the video capture device
        cap = initialize_capture_device(device_index)
        print(
            f"Camera {device_index} initialized at {CAPTURE_WIDTH}x{CAPTURE_HEIGHT} @ {CAPTURE_FPS} FPS."
        )

        # Start displaying the video feed
        show_camera(cap)
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
