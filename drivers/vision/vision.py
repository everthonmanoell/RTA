"""
Device Measurement System with AprilTags
=========================================
This program uses 4 AprilTags positioned at the corners of an area to:
1. Correct camera perspective (top-down transformation)
2. Calibrate real scale (pixels → cm)
3. Detect and measure smartphone dimensions automatically

Tag Layout:
   Tag 1 (top-left) -------- Tag 0 (top-right)
        |                          |
        |        DEVICE            |
        |                          |
   Tag 3 (bottom-left) ---- Tag 2 (bottom-right)
"""

import os
import time
from datetime import datetime

import cv2
import numpy as np
from pupil_apriltags import Detector

# ================= CONFIGURATION =================

# Real distances between internal corners of tags (measured with ruler)
# IMPORTANT: These measurements define the conversion scale
# Horizontal: Tag 1 corner[0] to Tag 0 corner[1]
DISTANCIA_REAL_LARGURA_CM = 8.09
# Vertical: Tag 1 corner[0] to Tag 3 corner[3]
DISTANCIA_REAL_ALTURA_CM = 15.13

# Directory configuration
SCRIPT_DIR = os.path.dirname(os.path.abspath(
    __file__))  # Directory where this script is located
# Directory to save images
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "detections_output")
os.makedirs(OUTPUT_DIR, exist_ok=True)  # Creates directory if it doesn't exist

# Anti-flood save control
SAVE_INTERVAL_SECONDS = 2.0  # Minimum interval between auto-saves
# True = saves on 's' key press | False = saves automatically
SAVE_ON_KEY = True
last_save_time = 0           # Timestamp of last save


def order_points(pts):
    """
    Order 4 points clockwise starting from top-left.

    Args:
        pts: Numpy array with 4 points (x, y)

    Returns:
        Ordered array: [top-left, top-right, bottom-right, bottom-left]
    """
    rect = np.zeros((4, 2), dtype="float32")

    # Superior esquerdo tem a menor soma de coordenadas (x+y)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]

    # Inferior direito tem a maior soma (x+y)
    rect[2] = pts[np.argmax(s)]

    # Superior direito tem a menor diferença (y-x)
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]

    # Inferior esquerdo tem a maior diferença (y-x)
    rect[3] = pts[np.argmax(diff)]

    return rect


def main():
    """Main function of the measurement system"""

    # ========== CAMERA INITIALIZATION ==========
    # Try to open camera 1 (external camera), if failed use camera 0 (webcam)
    cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

    # Configure resolution for better quality
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    # ========== APRILTAG DETECTOR INITIALIZATION ==========
    # Family tag36h11 is the most common (robust and reliable)
    detector = Detector(families='tag36h11')

    # ========== INITIAL MESSAGES ==========
    print("\n" + "="*60)
    print("📱 APRILTAG MEASUREMENT SYSTEM")
    print("="*60)
    print(f"\n📁 Save directory: {OUTPUT_DIR}")
    if SAVE_ON_KEY:
        print("⌨️  Press 's' to SAVE images | 'q' to EXIT")
    else:
        print(f"💾 Auto-save every {SAVE_INTERVAL_SECONDS}s")
    print("\n" + "="*60 + "\n")

    # ========== CONTROL VARIABLES ==========
    global last_save_time
    save_requested = False  # Flag to signal when user presses 's'

    # ========== MAIN LOOP ==========
    while True:
        # Capture frame from camera
        ret, frame = cap.read()
        if not ret:
            break  # If failed, end program

        # ========== STEP 1: APRILTAG DETECTION ==========
        # Convert to grayscale (apriltags are detected in black and white)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Detect all tags in the frame
        detections = detector.detect(gray)

        # Map tag ID → its 4 corners
        # Each tag has 4 corners indexed: [0]=top-left, [1]=top-right, [2]=bottom-right, [3]=bottom-left
        tag_corners_map = {}
        for detection in detections:
            tag_corners_map[detection.tag_id] = detection.corners

            # Draw red circle at tag center (for visualization)
            center = tuple(map(int, detection.center))
            cv2.circle(frame, center, 4, (0, 0, 255), -1)

        # ========== STEP 2: CHECK IF ALL 4 TAGS ARE PRESENT ==========
        if all(tid in tag_corners_map for tid in [0, 1, 2, 3]):
            try:
                # ========== STEP 3: EXTRACT INTERNAL CORNERS OF TAGS ==========
                # Each tag contributes 1 corner pointing inward to the area
                # pupil_apriltags library returns corners in this order:
                # [0]=top-left, [1]=top-right, [2]=bottom-right, [3]=bottom-left

                # Tag 1 (top-left) → get bottom-right corner [3]
                pt_tl = tag_corners_map[1][3]

                # Tag 0 (top-right) → get bottom-left corner [2]
                pt_tr = tag_corners_map[0][2]

                # Tag 2 (bottom-right) → get top-left corner [1]
                pt_br = tag_corners_map[2][1]

                # Tag 3 (bottom-left) → get top-right corner [0]
                pt_bl = tag_corners_map[3][0]

                # Draw MAGENTA circles on the 4 anchor points (visualization)
                for pt in [pt_tl, pt_tr, pt_br, pt_bl]:
                    cv2.circle(frame, tuple(map(int, pt)),
                               6, (255, 0, 255), -1)

            except KeyError:
                # If any tag was not detected correctly, skip this frame
                cv2.imshow("Original", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                continue

            # ========== STEP 4: PERSPECTIVE TRANSFORMATION ==========
            # Order points correctly (top-left, top-right, bottom-left, bottom-right)
            src_pts = order_points(np.float32([pt_tl, pt_tr, pt_bl, pt_br]))

            # Define scale: how many pixels represent 1 cm in reality
            # Larger scale = larger warped image = more precision
            escala = 20  # 20 pixels = 1 cm

            # Calculate corrected image dimensions in pixels
            w_pixels = int(DISTANCIA_REAL_LARGURA_CM * escala)
            h_pixels = int(DISTANCIA_REAL_ALTURA_CM * escala)

            # Define 4 destination points (perfect rectangle)
            dst_pts = np.float32([
                [0, 0],                    # top-left
                [w_pixels, 0],             # top-right
                [w_pixels, h_pixels],      # bottom-right
                [0, h_pixels]              # bottom-left
            ])

            # Calculate perspective transformation matrix
            matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)

            # Apply transformation → "top-down" image (bird's eye view)
            warped = cv2.warpPerspective(frame, matrix, (w_pixels, h_pixels))

            # ========== STEP 5: DEVICE DETECTION AND SEGMENTATION ==========
            # Convert to grayscale
            warped_gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)

            # Apply blur to reduce noise (low-pass filter)
            blurred = cv2.GaussianBlur(warped_gray, (5, 5), 0)

            # Automatic binarization (Otsu): convert to black and white
            # THRESH_BINARY_INV = dark objects become white
            _, thresh = cv2.threshold(
                blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

            # Morphological OPEN operation: removes small white noise
            kernel = np.ones((3, 3), np.uint8)
            thresh = cv2.morphologyEx(
                thresh, cv2.MORPH_OPEN, kernel, iterations=2)

            # Find contours (edges) of white objects
            contours, _ = cv2.findContours(
                thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            # Create a copy of warped image to draw results
            warped_display = warped.copy()

            # ========== STEP 6: CONTOUR FILTERING AND MEASUREMENT ==========
            # Iterate through all found contours
            for cnt in contours:
                # Calculate contour area in cm² (converts from pixels to cm)
                area_cm2 = cv2.contourArea(cnt) / (escala ** 2)

                # Size filter: ignore objects that are too small or too large
                # Too small < 20 cm² = noise/dirt
                # Too large > 95% of total area = background/sheet
                area_maxima = DISTANCIA_REAL_LARGURA_CM * DISTANCIA_REAL_ALTURA_CM * 0.95

                if area_cm2 > 20.0 and area_cm2 < area_maxima:
                    # Calculate minimum enclosing rectangle (may be rotated)
                    rect = cv2.minAreaRect(cnt)

                    # Convert to 4 points (rectangle corners)
                    box = np.intp(cv2.boxPoints(rect))

                    # Draw GREEN contour around device
                    cv2.drawContours(warped_display, [box], 0, (0, 255, 0), 3)

                    # Extract width and height of rectangle (in pixels)
                    (w, h) = rect[1]

                    # Convert to cm and format text
                    largura_cm = min(w, h) / escala
                    altura_cm = max(w, h) / escala
                    texto = f"{largura_cm:.2f}cm x {altura_cm:.2f}cm"

                    # Print dimensions to console (in real-time)
                    print(f"📱 Device: {texto}")

                    # Draw text on image (above rectangle)
                    cv2.putText(warped_display, texto, (box[0][0], box[0][1] - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            # ========== STEP 7: IMAGE SAVE LOGIC ==========
            # (Executed outside the contour loop to save only 1 time per frame)

            should_save = False
            current_time = time.time()

            # Manual mode: saves only when 's' is pressed
            if SAVE_ON_KEY and save_requested:
                should_save = True
                save_requested = False  # Reset flag

            # Auto mode: respects time interval (anti-flood)
            elif not SAVE_ON_KEY and (current_time - last_save_time > SAVE_INTERVAL_SECONDS):
                should_save = True

            # Execute save if flag is active
            if should_save:
                last_save_time = current_time
                ts = datetime.now().strftime("%H%M%S")
                print(f"\n💾 SAVING IMAGES [{ts}]...")

                # Save 3 images:
                # 1. mask = Binarized image (CRITICAL for debug: device should be white)
                cv2.imwrite(os.path.join(OUTPUT_DIR, f"mask_{ts}.jpg"), thresh)

                # 2. warp = Top-down view with measurements drawn
                cv2.imwrite(os.path.join(
                    OUTPUT_DIR, f"warp_{ts}.jpg"), warped_display)

                # 3. orig = Original camera frame (with tags marked)
                cv2.imwrite(os.path.join(OUTPUT_DIR, f"orig_{ts}.jpg"), frame)

                print(f"   ✅ Saved to: {OUTPUT_DIR}")
                print(f"   📄 mask_{ts}.jpg | warp_{ts}.jpg | orig_{ts}.jpg\n")

            # ========== STEP 8: WINDOW DISPLAY ==========
            cv2.imshow("Warped", warped_display)
            cv2.imshow("Mask", thresh)

        else:
            # If the 4 tags were NOT detected
            cv2.putText(frame, "Searching for tags... (need 4)", (10, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

        # Always show the original camera frame
        cv2.imshow("Original", frame)

        # ========== STEP 9: KEY CONTROL =========
        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            # Exit program
            break
        elif key == ord('s'):
            # Signal to save on next valid frame
            print("\n>> 'S' key pressed. Waiting for valid detection...\n")
            save_requested = True

    # ========== SHUTDOWN ==========
    cap.release()  # Release camera
    cv2.destroyAllWindows()  # Close all windows


if __name__ == "__main__":
    main()
