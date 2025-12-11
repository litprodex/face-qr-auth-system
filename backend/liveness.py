import base64
from typing import List

import cv2
import numpy as np
import mediapipe as mp


LEFT_EYE_IDX = [33, 160, 158, 133, 153, 144]
RIGHT_EYE_IDX = [263, 387, 385, 362, 380, 373]

EAR_THRESHOLD = 0.21
CONSEC_FRAMES_FOR_BLINK = 2


def _decode_base64_image(b64_string: str):
    """
    Przyjmuje data URL (data:image/jpeg;base64,...) lub czysty base64
    i zwraca obraz BGR (numpy array) lub None.
    """
    if "," in b64_string:
        b64_string = b64_string.split(",", 1)[1]

    try:
        img_data = base64.b64decode(b64_string)
        nparr = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img
    except Exception:
        return None


def _eye_aspect_ratio(landmarks, eye_indices, img_w: int, img_h: int) -> float:
    points = []
    for idx in eye_indices:
        lm = landmarks[idx]
        points.append(np.array([lm.x * img_w, lm.y * img_h]))

    p1, p2, p3, p4, p5, p6 = points
    # (|p2 - p6| + |p3 - p5|) / (2 * |p1 - p4|)
    numerator = np.linalg.norm(p2 - p6) + np.linalg.norm(p3 - p5)
    denominator = 2.0 * np.linalg.norm(p1 - p4)
    if denominator == 0:
        return 0.0
    return float(numerator / denominator)


def is_live_from_base64_frames(frames_b64: List[str]) -> bool:
    """
    Bardzo prosty test żywotności:
    - Dekoduje serię klatek.
    - Oblicza EAR (Eye Aspect Ratio) dla lewego i prawego oka.
    - Jeżeli w sekwencji nastąpi spadek EAR poniżej progu przez kilka klatek,
      uznajemy to za mrugnięcie -> osoba "żywa".
    """
    decoded_frames = []
    for b64 in frames_b64:
        img = _decode_base64_image(b64)
        if img is not None:
            decoded_frames.append(img)

    if len(decoded_frames) < 3:
        # za mało klatek, by sensownie ocenić mrugnięcie
        return False

    mp_face_mesh = mp.solutions.face_mesh

    blink_detected = False
    consec_below = 0

    with mp_face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5,
    ) as face_mesh:
        for img in decoded_frames:
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            result = face_mesh.process(rgb)

            if not result.multi_face_landmarks:
                consec_below = 0
                continue

            face_landmarks = result.multi_face_landmarks[0].landmark
            h, w, _ = img.shape

            left_ear = _eye_aspect_ratio(face_landmarks, LEFT_EYE_IDX, w, h)
            right_ear = _eye_aspect_ratio(face_landmarks, RIGHT_EYE_IDX, w, h)
            ear = (left_ear + right_ear) / 2.0

            if ear < EAR_THRESHOLD:
                consec_below += 1
                if consec_below >= CONSEC_FRAMES_FOR_BLINK:
                    blink_detected = True
            else:
                consec_below = 0

    return blink_detected


