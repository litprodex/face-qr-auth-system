(() => {
  const video = document.getElementById("adminCamera");
  const preview = document.getElementById("snapPreview");
  const faceB64Input = document.getElementById("faceImageB64");
  const fileInput = document.getElementById("face_image");

  const startBtn = document.getElementById("startCamBtn");
  const snapBtn = document.getElementById("snapBtn");
  const clearBtn = document.getElementById("clearSnapBtn");

  if (!video || !preview || !faceB64Input || !startBtn || !snapBtn || !clearBtn) {
    return;
  }

  let stream = null;

  async function startCamera() {
    if (stream) return;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user" },
        audio: false,
      });
      video.srcObject = stream;
      snapBtn.disabled = false;
    } catch (e) {
      console.error("Nie udało się uruchomić kamery:", e);
      alert("Nie udało się uruchomić kamery. Sprawdź uprawnienia przeglądarki.");
    }
  }

  function stopCamera() {
    if (!stream) return;
    stream.getTracks().forEach((t) => t.stop());
    stream = null;
    video.srcObject = null;
    snapBtn.disabled = true;
  }

  function captureSnapshot() {
    if (!video.videoWidth || !video.videoHeight) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.92);

    faceB64Input.value = dataUrl;
    preview.src = dataUrl;
    preview.style.display = "block";
    video.style.display = "none";
    clearBtn.disabled = false;

    // jeśli wybrano obraz z kamery, czyścimy upload pliku (żeby nie mieszać)
    if (fileInput) {
      fileInput.value = "";
    }
  }

  function clearSnapshot() {
    faceB64Input.value = "";
    preview.src = "";
    preview.style.display = "none";
    video.style.display = "block";
    clearBtn.disabled = true;
  }

  startBtn.addEventListener("click", startCamera);
  snapBtn.addEventListener("click", captureSnapshot);
  clearBtn.addEventListener("click", clearSnapshot);

  // jeśli użytkownik wybierze plik, czyścimy base64 z kamery
  if (fileInput) {
    fileInput.addEventListener("change", () => {
      if (fileInput.files && fileInput.files.length > 0) {
        clearSnapshot();
        stopCamera();
      }
    });
  }

  // Sprzątnie po odświeżeniu/nawigacji
  window.addEventListener("beforeunload", stopCamera);
})();


