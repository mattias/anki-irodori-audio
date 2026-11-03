"""Install and run a local Irodori-TTS server for the add-on.

No Anki imports here, so the module can be tested on its own. The UI in __init__.py calls
install() once and start()/stop() afterwards. Everything lives in one folder (default: a
folder in the user's local data directory) and nothing outside it is changed.
"""
import json
import os
import platform
import queue
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request
import zipfile

# The server source is pinned so that an install always gets the version this add-on was tested with.
SERVER_COMMIT = "61012c760f22f7b4a6c21c5c5f8f9e148120b6f9"
SERVER_ZIP_URL = f"https://github.com/Aratako/Irodori-TTS-Server/archive/{SERVER_COMMIT}.zip"
UV_BASE_URL = "https://github.com/astral-sh/uv/releases/latest/download/"
IS_WINDOWS = sys.platform == "win32"
CREATE_NO_WINDOW = 0x08000000
INSTALL_STEPS = 6


class Cancelled(Exception):
    pass


class SetupError(Exception):
    pass


def default_dir():
    if IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "IrodoriAudio")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/IrodoriAudio")
    return os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "irodori-audio")


class Paths:
    def __init__(self, root):
        self.root = root
        self.server = os.path.join(root, "server")
        self.bin = os.path.join(root, "bin")
        self.uv_dir = os.path.join(root, "uv")
        self.log = os.path.join(root, "server.log")
        self.marker = os.path.join(root, "installed.json")
        exe = "Scripts" if IS_WINDOWS else "bin"
        self.venv_python = os.path.join(self.server, ".venv", exe, "python.exe" if IS_WINDOWS else "python")


def is_installed(root):
    p = Paths(root)
    try:
        with open(p.marker, encoding="utf-8") as f:
            info = json.load(f)
    except Exception:
        return False
    return info.get("commit") == SERVER_COMMIT and os.path.exists(p.venv_python)


def clean_env(extra_path=None):
    """Environment for child processes, without Python settings that could leak in from Anki."""
    env = dict(os.environ)
    for key in ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONUSERBASE", "VIRTUAL_ENV", "PYTHONEXECUTABLE"):
        env.pop(key, None)
    env["PYTHONUTF8"] = "1"
    if extra_path:
        env["PATH"] = extra_path + os.pathsep + env.get("PATH", "")
    return env


def kill_tree(proc):
    if proc.poll() is not None:
        return
    try:
        if IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                creationflags=CREATE_NO_WINDOW,
                timeout=15,
            )
        else:
            os.killpg(proc.pid, signal.SIGTERM)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def run(cmd, cwd, env, log, cancelled):
    """Run a command, stream its output to log(line), kill it if cancelled() becomes true."""
    kwargs = {"creationflags": CREATE_NO_WINDOW} if IS_WINDOWS else {"start_new_session": True}
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        **kwargs,
    )
    lines = queue.Queue()

    def reader():
        for line in proc.stdout:
            lines.put(line.rstrip())
        lines.put(None)

    threading.Thread(target=reader, daemon=True).start()
    tail = []
    while True:
        if cancelled():
            kill_tree(proc)
            raise Cancelled()
        try:
            line = lines.get(timeout=0.3)
        except queue.Empty:
            continue
        if line is None:
            break
        tail = (tail + [line])[-15:]
        if line:
            log(line)
    code = proc.wait()
    if code != 0:
        raise SetupError(f"Command failed ({code}): {' '.join(cmd[:4])}\n" + "\n".join(tail[-8:]))


def download(url, dest, log, cancelled):
    req = urllib.request.Request(url, headers={"User-Agent": "irodori-audio-anki-addon"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got, next_report = 0, 0.1
        while True:
            if cancelled():
                raise Cancelled()
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if total and got / total >= next_report:
                log(f"  downloaded {got // (1 << 20)} of {total // (1 << 20)} MB")
                next_report += 0.2


def uv_archive_name():
    machine = platform.machine().lower()
    arm = machine in ("arm64", "aarch64")
    if IS_WINDOWS:
        return "uv-aarch64-pc-windows-msvc.zip" if arm else "uv-x86_64-pc-windows-msvc.zip"
    if sys.platform == "darwin":
        return "uv-aarch64-apple-darwin.tar.gz" if arm else "uv-x86_64-apple-darwin.tar.gz"
    return "uv-aarch64-unknown-linux-gnu.tar.gz" if arm else "uv-x86_64-unknown-linux-gnu.tar.gz"


def find_uv(paths, use_path=True):
    exe = "uv.exe" if IS_WINDOWS else "uv"
    local = os.path.join(paths.uv_dir, exe)
    if os.path.exists(local):
        return local
    return (shutil.which("uv") or None) if use_path else None


def ensure_uv(paths, log, cancelled, use_path=True):
    found = find_uv(paths, use_path)
    if found:
        log(f"Using uv: {found}")
        return found
    log("Downloading uv (the Python package manager the server needs)...")
    os.makedirs(paths.uv_dir, exist_ok=True)
    name = uv_archive_name()
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, name)
        download(UV_BASE_URL + name, archive, log, cancelled)
        wanted = "uv.exe" if IS_WINDOWS else "uv"
        if name.endswith(".zip"):
            with zipfile.ZipFile(archive) as z:
                z.extractall(tmp)
        else:
            with tarfile.open(archive) as t:
                t.extractall(tmp)
        for folder, _dirs, files in os.walk(tmp):
            if wanted in files:
                dest = os.path.join(paths.uv_dir, wanted)
                shutil.copy2(os.path.join(folder, wanted), dest)
                os.chmod(dest, 0o755)
                return dest
    raise SetupError("Could not find uv in the downloaded archive.")


def _nvidia_smi(*args):
    try:
        out = subprocess.run(
            ["nvidia-smi", *args],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=CREATE_NO_WINDOW if IS_WINDOWS else 0,
        )
        return out.stdout if out.returncode == 0 else ""
    except Exception:
        return ""


def gpu_capability():
    """Highest CUDA compute capability among the NVIDIA GPUs (e.g. 8.9), or None if unknown."""
    values = []
    for line in _nvidia_smi("--query-gpu=compute_cap", "--format=csv,noheader").splitlines():
        try:
            values.append(float(line.strip()))
        except ValueError:
            pass
    return max(values) if values else None


def detect_extra(preference="auto"):
    """'cu128' for a supported NVIDIA GPU (Windows/Linux), otherwise 'cpu'.

    The PyTorch CUDA 12.8 build has no kernels for GPUs older than compute capability 7.0
    (GTX 10 series and older), so those use the CPU build. preference 'cpu'/'cu128' overrides.
    """
    if preference in ("cpu", "cu128"):
        return preference
    if sys.platform == "darwin" or not shutil.which("nvidia-smi") or "GPU" not in _nvidia_smi("-L"):
        return "cpu"
    cap = gpu_capability()
    if cap is not None and cap < 7.0:
        return "cpu"
    return "cu128"


def installed_extra(root):
    try:
        with open(Paths(root).marker, encoding="utf-8") as f:
            return json.load(f).get("extra")
    except Exception:
        return None


def describe_backend(extra):
    cap = gpu_capability()
    if extra == "cu128":
        return "NVIDIA GPU found"
    if cap is not None and cap < 7.0:
        return f"your NVIDIA GPU (compute capability {cap}) is too old for the CUDA build, using the CPU, which is slow"
    return "no supported NVIDIA GPU, using the CPU, which is slow"


def fetch_server(paths, log, cancelled):
    log("Downloading the Irodori-TTS server code...")
    os.makedirs(paths.root, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "server.zip")
        download(SERVER_ZIP_URL, archive, log, cancelled)
        with zipfile.ZipFile(archive) as z:
            z.extractall(tmp)
        top = next(d for d in os.listdir(tmp) if os.path.isdir(os.path.join(tmp, d)))
        if os.path.exists(paths.server):
            shutil.rmtree(paths.server)
        shutil.move(os.path.join(tmp, top), paths.server)


def ensure_ffmpeg(paths, uv, env, log, cancelled):
    exe = "ffmpeg.exe" if IS_WINDOWS else "ffmpeg"
    if shutil.which("ffmpeg"):
        log("Using the ffmpeg that is already installed.")
        return
    target = os.path.join(paths.bin, exe)
    if os.path.exists(target):
        return
    log("Installing ffmpeg (needed for mp3 files)...")
    run([uv, "pip", "install", "--python", paths.venv_python, "imageio-ffmpeg"], paths.server, env, log, cancelled)
    found = subprocess.run(
        [paths.venv_python, "-c", "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"],
        capture_output=True,
        text=True,
        env=env,
        creationflags=CREATE_NO_WINDOW if IS_WINDOWS else 0,
    ).stdout.strip()
    if not found or not os.path.exists(found):
        raise SetupError("Could not find the ffmpeg binary after installing it.")
    os.makedirs(paths.bin, exist_ok=True)
    shutil.copy2(found, target)
    os.chmod(target, 0o755)


def install_voices(paths, voices_src, log):
    dest = os.path.join(paths.server, "voices")
    os.makedirs(dest, exist_ok=True)
    count = 0
    for name in os.listdir(voices_src):
        if name.lower().endswith(".wav"):
            shutil.copy2(os.path.join(voices_src, name), os.path.join(dest, name))
            count += 1
    if not count:
        raise SetupError(f"No voice files found in {voices_src}.")
    log(f"Installed {count} voice files.")


def install(root, voices_src, log, cancelled, step, extra=None):
    """One-time setup. step(n, total, label) reports progress. Safe to run again after a failure."""
    paths = Paths(root)
    os.makedirs(root, exist_ok=True)
    extra = extra or detect_extra()
    log(f"Install folder: {root}")
    log(f"Backend: {extra} ({describe_backend(extra)})")

    step(1, INSTALL_STEPS, "Getting uv")
    uv = ensure_uv(paths, log, cancelled)
    env = clean_env()

    step(2, INSTALL_STEPS, "Downloading the server code")
    fetch_server(paths, log, cancelled)

    step(3, INSTALL_STEPS, "Installing Python packages (about 5 GB, this takes a while)")
    run([uv, "sync", "--extra", extra], paths.server, env, log, cancelled)

    step(4, INSTALL_STEPS, "Installing ffmpeg")
    ensure_ffmpeg(paths, uv, env, log, cancelled)

    step(5, INSTALL_STEPS, "Installing voices")
    install_voices(paths, voices_src, log)

    with open(paths.marker, "w", encoding="utf-8") as f:
        json.dump({"commit": SERVER_COMMIT, "extra": extra}, f)
    step(INSTALL_STEPS, INSTALL_STEPS, "Done")


def health(url, timeout=2):
    try:
        with urllib.request.urlopen(url + "/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def port_of(url):
    tail = url.rsplit(":", 1)[-1].split("/")[0]
    return int(tail) if tail.isdigit() else 8088


def is_local(url):
    return url.split("://", 1)[-1].split(":")[0].split("/")[0] in ("127.0.0.1", "localhost")


def log_tail(paths, n=12):
    try:
        with open(paths.log, encoding="utf-8", errors="replace") as f:
            text = "".join(f.readlines()[-n:])
    except Exception:
        return ""
    if "no kernel image" in text:
        text += (
            "\nYour GPU is not supported by the CUDA build of PyTorch. "
            "Set BACKEND to \"cpu\" in the add-on config and run Tools > Irodori Audio > Set up local server again."
        )
    return text


def start(root, url, log, cancelled, timeout=900):
    """Start the server on 127.0.0.1 and wait until it answers. Returns the process (None if one already runs)."""
    paths = Paths(root)
    if health(url):
        return None
    if not is_installed(root):
        raise SetupError("The server is not installed yet.")
    env = clean_env(paths.bin)
    env["IRODORI_PRELOAD"] = "true"  # load the model at startup so the first sentence is fast
    cmd = [paths.venv_python, "-m", "irodori_openai_tts", "--host", "127.0.0.1", "--port", str(port_of(url))]
    logfile = open(paths.log, "w", encoding="utf-8")
    kwargs = {"creationflags": CREATE_NO_WINDOW} if IS_WINDOWS else {"start_new_session": True}
    proc = subprocess.Popen(
        cmd, cwd=paths.server, env=env, stdout=logfile, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **kwargs
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cancelled():
            kill_tree(proc)
            raise Cancelled()
        if proc.poll() is not None:
            raise SetupError("The server stopped while starting.\n\n" + log_tail(paths))
        if health(url):
            log("Server is ready.")
            return proc
        time.sleep(1)
    kill_tree(proc)
    raise SetupError("The server did not become ready in time.\n\n" + log_tail(paths))


def stop(proc):
    if proc is not None:
        kill_tree(proc)
