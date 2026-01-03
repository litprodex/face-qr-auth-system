import os
from backend.face_utils import add_user_with_image

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))  # katalog projektu
db_path = os.path.join(base_dir, "backend", "database.sqlite3")

user_id = add_user_with_image(
    db_path=db_path,
    name="Mati A",
    qr_code="MATI123",              # to będzie treść Twojego kodu QR
    image_path=r"C:\Users\mateo\OneDrive\Pulpit\face-qr-auth-system\mati.jpg"
)

print("Dodano usera o ID:", user_id)