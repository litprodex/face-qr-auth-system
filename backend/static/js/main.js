const video = document.getElementById("camera");
const canvas = document.getElementById("captureCanvas");
const startBtn = document.getElementById("startVerificationBtn");
const statusMessage = document.getElementById("statusMessage");
const overlay = document.getElementById("overlay");
const qrInput = document.getElementById("qrInput");

async function initCamera() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user" },
      audio: false,
    });
    video.srcObject = stream;
  } catch (err) {
    console.error("Błąd przy dostępie do kamery:", err);
    setStatus(
      "Nie udało się uzyskać dostępu do kamery. Sprawdź uprawnienia przeglądarki.",
      "error"
    );
  }
}

function setStatus(text, type = "") {
  statusMessage.textContent = text;
  statusMessage.classList.remove("success", "error");
  overlay.classList.remove("success", "error");

  if (type === "success") {
    statusMessage.classList.add("success");
    overlay.classList.add("success");
  } else if (type === "error") {
    statusMessage.classList.add("error");
    overlay.classList.add("error");
  }
}

function captureFrames(durationMs = 2500, fps = 8) {
  return new Promise((resolve) => {
    const frames = [];
    const intervalMs = 1000 / fps;
    const totalFrames = Math.floor(durationMs / intervalMs);

    const ctx = canvas.getContext("2d");
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;

    let captured = 0;

    const interval = setInterval(() => {
      if (captured >= totalFrames) {
        clearInterval(interval);
        resolve(frames);
        return;
      }

      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const dataUrl = canvas.toDataURL("image/jpeg");
      frames.push(dataUrl);
      captured++;
    }, intervalMs);
  });
}

async function handleVerification() {
  const qrCode = qrInput.value.trim();
  if (!qrCode) {
    setStatus("Wprowadź najpierw kod QR użytkownika.", "error");
    return;
  }

  setStatus(
    "Nagrywam krótką sekwencję — patrz w kamerę i mrugnij oczami...",
    ""
  );
  startBtn.disabled = true;

  try {
    const frames = await captureFrames();

    setStatus("Analizuję mrugnięcie i tożsamość, proszę czekać...");

    const res = await fetch("/verify", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        qr_code: qrCode,
        frames,
      }),
    });

    const json = await res.json();

    if (json.status === "success") {
      setStatus(json.message || "Autoryzacja zakończona sukcesem.", "success");
    } else if (json.status === "spoofing") {
      setStatus(
        json.message ||
          "Wykryto próbę oszustwa (spoofing) – brak naturalnego mrugnięcia.",
        "error"
      );
    } else if (json.status === "fraud") {
      setStatus(
        json.message || "Niepoprawna tożsamość powiązana z kodem QR.",
        "error"
      );
    } else {
      setStatus(json.message || "Wystąpił błąd podczas weryfikacji.", "error");
    }
  } catch (err) {
    console.error("Błąd przy wywołaniu /verify:", err);
    setStatus("Błąd połączenia z serwerem weryfikacji.", "error");
  } finally {
    startBtn.disabled = false;
  }
}

startBtn.addEventListener("click", handleVerification);

window.addEventListener("load", () => {
  initCamera();
  setStatus("Ustaw twarz w ramce i przygotuj się do mrugnięcia.");
});


