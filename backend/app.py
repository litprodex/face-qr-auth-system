import os
import base64
import json
from datetime import datetime

from flask import Flask, request, jsonify, render_template

from .database import init_db, get_user_by_qr, insert_log
from .liveness import is_live_from_base64_frames
from .face_utils import compare_face_with_user


def create_app():
    base_dir = os.path.abspath(os.path.dirname(__file__))
    db_path = os.path.join(base_dir, "database.sqlite3")

    app = Flask(
        __name__,
        template_folder=os.path.join(base_dir, "templates"),
        static_folder=os.path.join(base_dir, "static"),
    )
    app.config["DATABASE_PATH"] = db_path

    # Ensure DB exists
    init_db(db_path)

    @app.route("/", methods=["GET"])
    def index():
        return render_template("index.html")

    @app.route("/verify", methods=["POST"])
    def verify():
        data = request.get_json(silent=True) or {}
        qr_code = data.get("qr_code")
        frames = data.get("frames", [])

        if not qr_code or not frames:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Brak wymaganych danych (kod QR lub klatki wideo).",
                    }
                ),
                400,
            )

        db_path_local = app.config["DATABASE_PATH"]

        # 1. Liveness check
        is_live = is_live_from_base64_frames(frames)
        if not is_live:
            insert_log(db_path_local, None, datetime.utcnow(), "Spoofing")
            return (
                jsonify(
                    {
                        "status": "spoofing",
                        "message": "Wykryto próbę oszustwa (Spoofing) – brak mrugnięcia.",
                    }
                ),
                200,
            )

        # 2. Identyfikacja po kodzie QR i porównanie twarzy
        user = get_user_by_qr(db_path_local, qr_code)
        if not user:
            insert_log(db_path_local, None, datetime.utcnow(), "Oszustwo")
            return (
                jsonify(
                    {
                        "status": "fraud",
                        "message": "Nie znaleziono użytkownika o podanym kodzie QR.",
                    }
                ),
                200,
            )

        # używamy ostatniej klatki jako referencji do identyfikacji
        last_frame_b64 = frames[-1]
        is_match = compare_face_with_user(db_path_local, user, last_frame_b64)

        if not is_match:
            insert_log(db_path_local, user["id"], datetime.utcnow(), "Oszustwo")
            return (
                jsonify(
                    {
                        "status": "fraud",
                        "message": "Twarz nie pasuje do użytkownika powiązanego z kodem QR.",
                    }
                ),
                200,
            )

        # 3. Zapis logu – sukces
        insert_log(db_path_local, user["id"], datetime.utcnow(), "Sukces")

        return jsonify(
            {
                "status": "success",
                "message": f"Użytkownik {user['name']} poprawnie zweryfikowany.",
            }
        )

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)


