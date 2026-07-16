#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════╗
║         DIOT — Instalador Automático             ║
║  usbipd · ESP-IDF v6.0.1 · ESP-Matter           ║
╚══════════════════════════════════════════════════╝
Uso: python3 install_diot.py
     (o directamente: ./install_diot.py)
"""

import sys
import os
import shlex
import subprocess
import threading
import time
import json
import re
import shutil
import grp
from pathlib import Path

# ─────────────────────────────────────────────────
#  Colores ANSI
# ─────────────────────────────────────────────────
BOX_WIDTH = 54  # inner width (between ║ characters) for all UI boxes

WINGET_USBIPD_CMD = (
    "winget install --id dorssel.usbipd-win -e "
    "--accept-source-agreements --accept-package-agreements"
)

RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
RED     = "\033[91m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
BLUE    = "\033[94m"
MAGENTA = "\033[95m"
CYAN    = "\033[96m"
WHITE   = "\033[97m"

def c(color, text):
    return f"{color}{text}{RESET}"

def header(text):
    width = BOX_WIDTH
    print()
    print(c(CYAN, "╔" + "═" * width + "╗"))
    for line in text.strip().splitlines():
        line = line.strip()
        padding = width - len(line)
        left  = padding // 2
        right = padding - left
        print(c(CYAN, "║") + " " * left + c(BOLD + WHITE, line) + " " * right + c(CYAN, "║"))
    print(c(CYAN, "╚" + "═" * width + "╝"))
    print()

def info(msg):
    print(f"  {c(BLUE, '→')} {msg}")

def success(msg):
    print(f"  {c(GREEN, '✔')} {c(GREEN, msg)}")

def warn(msg):
    print(f"  {c(YELLOW, '⚠')} {c(YELLOW, msg)}")

def error(msg):
    print(f"\n  {c(RED, '✖')} {c(RED + BOLD, msg)}")

def step_banner(n, total, title):
    pct = int(n / total * 100)
    bar_len = 30
    filled = int(bar_len * n / total)
    bar = c(GREEN, "█" * filled) + c(DIM, "░" * (bar_len - filled))
    print()
    print(c(CYAN, f"  ┌─ Paso {n}/{total}") + f"  [{bar}] {c(BOLD, str(pct) + '%')}")
    print(c(CYAN,  f"  └─ ") + c(BOLD + WHITE, title))
    print()

# ─────────────────────────────────────────────────
#  Sistema de checkpoints
# ─────────────────────────────────────────────────
CHECKPOINT_FILE = Path.home() / ".diot_install_checkpoints.json"

def load_checkpoints():
    if CHECKPOINT_FILE.exists():
        try:
            with open(CHECKPOINT_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}

def mark_done(step):
    cp = load_checkpoints()
    cp[step] = True
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(cp, f, indent=2)

def is_done(step):
    return load_checkpoints().get(step, False)

def reset_checkpoints():
    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()

# ─────────────────────────────────────────────────
#  Spinner animado
# ─────────────────────────────────────────────────
class Spinner:
    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, label=""):
        self.label   = label
        self._stop   = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def _spin(self):
        idx = 0
        while not self._stop.is_set():
            frame = c(CYAN, self.FRAMES[idx % len(self.FRAMES)])
            sys.stdout.write(f"\r  {frame} {self.label} …")
            sys.stdout.flush()
            time.sleep(0.08)
            idx += 1

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join()
        sys.stdout.write("\r" + " " * (len(self.label) + 12) + "\r")
        sys.stdout.flush()

# ─────────────────────────────────────────────────
#  Ejecución de comandos
# ─────────────────────────────────────────────────
def run(cmd, shell=False, capture=False, env=None, cwd=None, stream=False):
    """
    Ejecuta un comando.
    - capture=True  → devuelve (rc, stdout, stderr)
    - stream=True   → imprime la salida en tiempo real
    """
    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    if capture:
        result = subprocess.run(
            cmd, shell=shell, capture_output=True,
            text=True, env=run_env, cwd=cwd
        )
        return result.returncode, result.stdout, result.stderr

    if stream:
        proc = subprocess.Popen(
            cmd, shell=shell, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True,
            env=run_env, cwd=cwd, bufsize=1
        )
        lines = []
        last_pct = -1
        for line in proc.stdout:
            lines.append(line)
            # Detectar porcentaje en salida de git / ninja
            m = re.search(r"(\d{1,3})%", line)
            if m:
                pct = int(m.group(1))
                if pct != last_pct:
                    last_pct = pct
                    bar_len = 28
                    filled = int(bar_len * pct / 100)
                    bar = c(GREEN, "█" * filled) + c(DIM, "░" * (bar_len - filled))
                    sys.stdout.write(f"\r    [{bar}] {c(BOLD, str(pct) + '%')}  ")
                    sys.stdout.flush()
            else:
                # Mostrar líneas relevantes (no spam)
                stripped = line.strip()
                if stripped and not stripped.startswith("remote:"):
                    short = stripped[:80]
                    sys.stdout.write(f"\r    {c(DIM, short):<84}\n")
                    sys.stdout.flush()
        if last_pct >= 0:
            sys.stdout.write("\n")
        proc.wait()
        return proc.returncode, "".join(lines), ""

    result = subprocess.run(
        cmd, shell=shell, text=True, env=run_env, cwd=cwd
    )
    return result.returncode, "", ""

def run_ok(cmd, **kw):
    """Ejecuta y aborta si hay error."""
    rc, out, err = run(cmd, **kw)
    if rc != 0:
        error(f"Fallo al ejecutar: {cmd if isinstance(cmd, str) else ' '.join(cmd)}")
        if err.strip():
            print(c(DIM, err.strip()))
        sys.exit(1)
    return out


def run_bash(script, capture=False, cwd=None, stream=False, env=None):
    """Ejecuta un script en bash -lc para permitir `source`/`BASH_SOURCE`."""
    return run(["bash", "-lc", script], capture=capture, cwd=cwd, stream=stream, env=env)

# ─────────────────────────────────────────────────
#  sudo keep-alive
# ─────────────────────────────────────────────────
_sudo_alive = threading.Event()

def _keep_sudo_alive():
    while not _sudo_alive.is_set():
        result = subprocess.run(
            ["sudo", "-n", "true"], capture_output=True
        )
        if result.returncode != 0:
            warn(
                "Las credenciales sudo han expirado durante la instalación. "
                "Es posible que los próximos pasos que requieran sudo fallen."
            )
        time.sleep(50)

def request_sudo():
    info("Se necesita contraseña de sudo para la instalación.")
    info("Será solicitada una sola vez.")
    print()
    rc = subprocess.call(["sudo", "-v"])
    if rc != 0:
        error("No se pudo obtener privilegios sudo. Abortando.")
        sys.exit(1)
    t = threading.Thread(target=_keep_sudo_alive, daemon=True)
    t.start()
    success("Privilegios sudo obtenidos.")

# ─────────────────────────────────────────────────
#  PASO 1 — Verificar WSL 2
# ─────────────────────────────────────────────────
def check_wsl2():
    step_banner(1, TOTAL_STEPS, "Verificar entorno WSL 2")

    if is_done("check_wsl2"):
        success("WSL 2 ya verificado (checkpoint).")
        return

    # Verificar que estamos dentro de WSL
    if not Path("/proc/version").exists():
        error("No se detectó un entorno Linux. Este script está diseñado para WSL.")
        sys.exit(1)

    proc_ver = Path("/proc/version").read_text()
    if "microsoft" not in proc_ver.lower() and "wsl" not in proc_ver.lower():
        error("Este script debe ejecutarse dentro de WSL (Windows Subsystem for Linux).")
        sys.exit(1)

    info("Detectado entorno WSL. Comprobando versión…")

    # Intentar obtener la versión de WSL desde Windows
    wsl_exe = shutil.which("wsl.exe") or "/mnt/c/Windows/System32/wsl.exe"
    if not Path(wsl_exe).exists():
        warn("No se encontró wsl.exe en la ruta estándar.")
        warn("Asumiendo WSL 2 (no se puede verificar sin wsl.exe).")
        mark_done("check_wsl2")
        return

    rc, out, err = run([wsl_exe, "-l", "-v"], capture=True)
    combined = (out + err).strip()
    info(f"Salida wsl -l -v:\n{c(DIM, combined)}")

    # Buscar la distribución activa (marcada con '*').
    # The wsl -l -v output format is:
    #   * Ubuntu-22.04   Running   2
    # The version is the last whitespace-delimited token on the line.
    wsl_version = None
    for line in combined.splitlines():
        if "*" in line:
            # Extract the last token on the line as the WSL version number
            tokens = line.split()
            if tokens:
                last_token = tokens[-1]
                if re.fullmatch(r"[1-9]\d*", last_token):
                    wsl_version = int(last_token)
            break

    if wsl_version is None:
        warn("No se pudo determinar la versión de WSL con seguridad.")
        warn("Continuando de todas formas…")
    elif wsl_version < 2:
        error(
            f"La distribución activa está usando WSL {wsl_version}, se requiere WSL 2 o superior.\n"
            f"  Ejecuta en PowerShell (como administrador):\n"
            f"    wsl --set-version <NombreDistro> 2\n"
            f"    wsl --set-default-version 2"
        )
        sys.exit(1)
    else:
        success(f"WSL versión {wsl_version} confirmado.")

    mark_done("check_wsl2")

# ─────────────────────────────────────────────────
#  PASO 2 — Verificar Ubuntu 24+
# ─────────────────────────────────────────────────
def check_ubuntu_version():
    step_banner(2, TOTAL_STEPS, "Verificar Ubuntu 24+")

    if is_done("check_ubuntu_version"):
        success("Versión de Ubuntu ya verificada (checkpoint).")
        return

    if not Path("/etc/os-release").exists():
        error("No se encontró /etc/os-release. ¿Es esto Ubuntu?")
        sys.exit(1)

    os_info = Path("/etc/os-release").read_text()
    info(f"Sistema detectado:\n{c(DIM, os_info.strip())}")

    id_match  = re.search(r'^ID="?([^"\n]+)"?', os_info, re.M)
    ver_match = re.search(r'^VERSION_ID="?([^"\n]+)"?', os_info, re.M)

    if not id_match or "ubuntu" not in id_match.group(1).lower():
        error("Este script requiere Ubuntu. Sistema detectado: "
              + (id_match.group(1) if id_match else "desconocido"))
        sys.exit(1)

    if ver_match:
        try:
            major = int(ver_match.group(1).split(".")[0])
        except ValueError:
            warn("No se pudo interpretar el número de versión de Ubuntu. Continuando…")
            mark_done("check_ubuntu_version")
            return
        if major < 24:
            error(
                f"Ubuntu {ver_match.group(1)} detectado. Se requiere Ubuntu 24 o superior.\n"
                "  Por favor actualiza tu distribución WSL."
            )
            sys.exit(1)
        success(f"Ubuntu {ver_match.group(1)} ✔")
    else:
        warn("No se pudo determinar la versión exacta de Ubuntu. Continuando…")

    mark_done("check_ubuntu_version")

# ─────────────────────────────────────────────────
#  PASO 3 — apt update && apt upgrade
# ─────────────────────────────────────────────────
def apt_update_upgrade():
    step_banner(3, TOTAL_STEPS, "Actualizar paquetes del sistema (apt)")

    if is_done("apt_update_upgrade"):
        success("apt update/upgrade ya completado (checkpoint).")
        return

    info("Ejecutando sudo apt update…")
    with Spinner("apt update"):
        rc, out, err = run(
            ["sudo", "apt", "update", "-y"],
            capture=True
        )
    if rc != 0:
        error("apt update falló. Posibles causas: sin acceso a internet, repositorio no disponible.")
        output = (out + err).strip()
        if output:
            print(c(DIM, output))
        sys.exit(1)
    success("apt update completado.")

    info("Ejecutando sudo apt upgrade -y  (puede tardar varios minutos)…")
    rc, _, _ = run(
        ["sudo", "apt", "upgrade", "-y",
         "-o", "Dpkg::Options::=--force-confdef",
         "-o", "Dpkg::Options::=--force-confold"],
        stream=True
    )
    if rc != 0:
        error("apt upgrade falló. Revisa los errores anteriores.")
        sys.exit(1)
    success("apt upgrade completado.")

    mark_done("apt_update_upgrade")

# ─────────────────────────────────────────────────
#  PASO 4 — Instalar EIM (ESP-IDF Installation Manager)
# ─────────────────────────────────────────────────
def install_eim():
    step_banner(4, TOTAL_STEPS, "Instalar EIM — ESP-IDF Installation Manager")

    if is_done("install_eim"):
        success("EIM ya instalado (checkpoint).")
        return

    info("Añadiendo repositorio Espressif a APT sources…")
    # Note: [trusted=yes] is the method documented in Espressif's official
    # installation guide (https://docs.espressif.com/projects/esp-idf/).
    # For tighter security, you could instead import the Espressif GPG key
    # and replace [trusted=yes] with [signed-by=/etc/apt/keyrings/espressif.gpg].
    rc, _, _ = run(
        'echo "deb [trusted=yes] https://dl.espressif.com/dl/eim/apt/ stable main" '
        '| sudo tee /etc/apt/sources.list.d/espressif.list',
        shell=True, capture=True
    )
    if rc != 0:
        error("No se pudo añadir el repositorio EIM.")
        sys.exit(1)
    success("Repositorio EIM añadido.")

    info("Actualizando lista de paquetes…")
    with Spinner("apt update"):
        rc_update, out, err = run(["sudo", "apt", "update", "-y"], capture=True)
    if rc_update != 0:
        warn("apt update falló tras añadir el repositorio EIM.")
        warn("Saltando instalación de EIM — ESP-IDF será instalado directamente con git.")
        mark_done("install_eim")
        return
    success("Lista de paquetes actualizada.")

    info("Instalando eim-cli…")
    with Spinner("instalando eim-cli"):
        rc, out, err = run(
            ["sudo", "apt", "install", "-y", "eim-cli"],
            capture=True
        )
    if rc != 0:
        warn("eim-cli no disponible, intentando con 'eim'…")
        with Spinner("instalando eim"):
            rc, out, err = run(
                ["sudo", "apt", "install", "-y", "eim"],
                capture=True
            )
        if rc != 0:
            warn("No se pudo instalar EIM vía apt. Continuando sin EIM.")
            warn("  ESP-IDF será instalado directamente con git.")
        else:
            success("EIM instalado.")
    else:
        success("eim-cli instalado.")

    mark_done("install_eim")

# ─────────────────────────────────────────────────
#  PASO 5 — Instalar usbipd (lado Windows)
# ─────────────────────────────────────────────────
def install_usbipd():
    step_banner(5, TOTAL_STEPS, "Instalar usbipd-win (lado Windows)")

    if is_done("install_usbipd"):
        success("usbipd ya instalado (checkpoint).")
        return

    info("usbipd se instala en Windows (no en WSL).")
    info("Lanzando 'winget install usbipd' desde PowerShell…")

    # Buscar powershell.exe en rutas de Windows accesibles desde WSL
    ps_candidates = [
        "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
        "/mnt/c/Windows/SysNative/WindowsPowerShell/v1.0/powershell.exe",
    ]
    ps_exe = next((p for p in ps_candidates if Path(p).exists()), None)

    if ps_exe is None:
        ps_exe = shutil.which("powershell.exe")

    if ps_exe is None:
        warn("No se encontró powershell.exe. ¿Estás realmente en WSL?")
        warn("Salteando instalación automática de usbipd.")
        warn("Por favor instálalo manualmente desde PowerShell (admin):")
        warn(f"    {WINGET_USBIPD_CMD}")
        mark_done("install_usbipd")
        return

    info(f"PowerShell encontrado: {ps_exe}")
    info("Ejecutando winget install usbipd (puede pedir confirmación)…")
    print()

    # -NoProfile: skips the user's PowerShell profile scripts so this non-interactive
    # call doesn't block waiting for user input or fail due to interactive-only profiles.
    # Security trade-off: this also bypasses any execution-policy restrictions set in
    # the user's profile. If your environment enforces strict execution policies for
    # security reasons, run the following command manually in an admin PowerShell instead:
    #   Set-ExecutionPolicy Bypass -Scope Process -Force; <WINGET_USBIPD_CMD>
    # winget validates packages with its own signature checking (Microsoft Store).
    rc, out, err = run(
        [ps_exe, "-NoProfile", "-Command", WINGET_USBIPD_CMD],
        capture=True
    )
    combined = (out + err).strip()
    if combined:
        for line in combined.splitlines():
            print(c(DIM, f"    {line}"))
    print()

    if rc != 0:
        warn("winget puede haber retornado un error no crítico (p.ej., ya estaba instalado).")
        warn("Verifica manualmente con: winget list usbipd")
    else:
        success("usbipd instalado en Windows.")

    info("Para conectar tu dispositivo USB a WSL después de instalar, ejecuta en PowerShell:")
    info("    usbipd list")
    info("    usbipd bind --busid <BUSID>")
    info("    usbipd attach --wsl --busid <BUSID>")

    mark_done("install_usbipd")

# ─────────────────────────────────────────────────
#  PASO 6 — Instalar dependencias de build en Ubuntu
# ─────────────────────────────────────────────────
def install_build_deps():
    step_banner(6, TOTAL_STEPS, "Instalar dependencias de build en Ubuntu")

    if is_done("install_build_deps"):
        success("Dependencias de build ya instaladas (checkpoint).")
        return

    packages = [
        "git", "wget", "flex", "bison", "gperf",
        "python3", "python3-pip", "python3-venv", "python3-setuptools",
        "cmake", "ninja-build", "ccache",
        "libffi-dev", "libssl-dev", "dfu-util",
        "libusb-1.0-0",
    ]
    info("Instalando paquetes: " + " ".join(packages))
    rc, out, err = run(
        ["sudo", "apt", "install", "-y"] + packages,
        stream=True
    )
    if rc != 0:
        error("Error instalando dependencias de build.")
        print(c(DIM, err))
        sys.exit(1)
    success("Todas las dependencias de build instaladas.")

    mark_done("install_build_deps")

# ─────────────────────────────────────────────────
#  PASO 7 — Clonar e instalar ESP-IDF v6.0.1
# ─────────────────────────────────────────────────
def install_esp_idf():
    step_banner(7, TOTAL_STEPS, "Instalar ESP-IDF v6.0.1")

    esp_dir     = Path.home() / "esp"
    idf_dir     = esp_dir / "esp-idf"
    idf_version = "v6.0.1"

    if is_done("clone_esp_idf"):
        success("ESP-IDF ya clonado (checkpoint).")
    else:
        esp_dir.mkdir(parents=True, exist_ok=True)
        if idf_dir.exists():
            warn(f"{idf_dir} ya existe. Usando el directorio existente.")
        else:
            info(f"Clonando ESP-IDF {idf_version} (con submódulos — puede tardar)…")
            print()
            rc, _, _ = run(
                ["git", "clone", "--progress",
                 "-b", idf_version, "--recursive",
                 "https://github.com/espressif/esp-idf.git",
                 str(idf_dir)],
                stream=True
            )
            if rc != 0:
                error("No se pudo clonar ESP-IDF.")
                sys.exit(1)
            success("ESP-IDF clonado.")
        mark_done("clone_esp_idf")

    if is_done("install_esp_idf_tools"):
        success("Herramientas ESP-IDF ya instaladas (checkpoint).")
    else:
        info("Ejecutando install.sh esp32c6 (descarga toolchain — puede tardar)…")
        print()
        rc, _, _ = run(
            ["bash", "install.sh", "esp32c6"],
            cwd=str(idf_dir),
            stream=True
        )
        if rc != 0:
            error("install.sh falló.")
            sys.exit(1)
        success("Herramientas ESP-IDF instaladas.")
        mark_done("install_esp_idf_tools")

    if is_done("verify_esp_idf"):
        success("ESP-IDF ya verificado (checkpoint).")
    else:
        info("Verificando versión de idf.py…")

        # Sourcing export.sh sets IDF_PATH and PATH within the subshell.
        # run() starts from os.environ.copy() so all existing env vars are preserved.
        idf_q = shlex.quote(str(idf_dir))
        rc, out, err = run_bash(
            f'source {idf_q}/export.sh && idf.py --version',
            capture=True,
        )
        version_line = (out + err).strip().splitlines()
        for line in version_line:
            if "idf.py" in line.lower() or "esp-idf" in line.lower() or "v" in line:
                info(line)
        success("ESP-IDF instalado correctamente.")
        mark_done("verify_esp_idf")

# ─────────────────────────────────────────────────
#  PASO 8 — Clonar e inicializar ESP-Matter
# ─────────────────────────────────────────────────
def install_esp_matter():
    step_banner(8, TOTAL_STEPS, "Instalar ESP-Matter (proceso largo ~30 min)")

    esp_dir    = Path.home() / "esp"
    matter_dir = esp_dir / "esp-matter"
    idf_dir    = esp_dir / "esp-idf"

    if is_done("clone_esp_matter"):
        success("ESP-Matter ya clonado (checkpoint).")
    else:
        esp_dir.mkdir(parents=True, exist_ok=True)
        if matter_dir.exists():
            warn(f"{matter_dir} ya existe. Usando el directorio existente.")
        else:
            warn("ESP-Matter tiene muchos submódulos. La descarga puede tardar 30+ minutos.")
            info("Clonando ESP-Matter con submódulos recursivos…")
            print()
            rc, _, _ = run(
                ["git", "clone", "--progress",
                 "--recursive",
                 "https://github.com/espressif/esp-matter.git",
                 str(matter_dir)],
                stream=True
            )
            if rc != 0:
                error("No se pudo clonar ESP-Matter.")
                sys.exit(1)
            success("ESP-Matter clonado.")
        mark_done("clone_esp_matter")

    info("Asegurando submódulos de ESP-Matter (idempotente)…")
    rc, _, _ = run(["git", "submodule", "sync", "--recursive"], cwd=str(matter_dir), stream=True)
    if rc != 0:
        error("git submodule sync falló en ESP-Matter.")
        sys.exit(1)

    rc, _, _ = run(["git", "submodule", "update", "--init", "--recursive"], cwd=str(matter_dir), stream=True)
    if rc != 0:
        error("git submodule update --init --recursive falló en ESP-Matter.")
        sys.exit(1)

    if is_done("export_esp_matter"):
        success("ESP-Matter ya exportado/inicializado (checkpoint).")
    else:
        info("Ejecutando export.sh de ESP-Matter (inicializa Matter SDK)…")
        warn("Este paso puede tardar varios minutos la primera vez.")
        print()
        idf_q    = shlex.quote(str(idf_dir))
        matter_q = shlex.quote(str(matter_dir))
        # run() preserves os.environ; export.sh sets IDF_PATH/PATH inside the subshell.
        rc, _, _ = run_bash(
            f'source {idf_q}/export.sh && export ESP_MATTER_PATH={matter_q} && source {matter_q}/export.sh',
            stream=True,
        )
        if rc != 0:
            error("export.sh de ESP-Matter falló.")
            sys.exit(1)
        success("ESP-Matter inicializado.")
        mark_done("export_esp_matter")



def ensure_gn_available(idf_dir: Path, matter_dir: Path):
    """Verifica que `gn` esté disponible; intenta bootstrap si falta."""
    idf_q = shlex.quote(str(idf_dir))
    matter_q = shlex.quote(str(matter_dir))

    rc, out, err = run_bash(
        f'source {idf_q}/export.sh && export ESP_MATTER_PATH={matter_q} && '
        f'source {matter_q}/export.sh && command -v gn',
        capture=True,
    )
    gn_path = (out + err).strip().splitlines()
    if rc == 0 and gn_path:
        success(f"GN disponible: {gn_path[-1]}")
        return

    warn("No se encontró 'gn' en PATH. Intentando bootstrap de Matter SDK…")

    chip_dir = matter_dir / 'connectedhomeip' / 'connectedhomeip'
    if not chip_dir.exists():
        error(f"No se encontró connectedhomeip en: {chip_dir}")
        sys.exit(1)

    chip_q = shlex.quote(str(chip_dir))
    info("Bootstrap de Matter SDK en curso (descarga paquetes CIPD; puede tardar varios minutos)…")
    rc, _, _ = run_bash(
        f'cd {chip_q} && source scripts/bootstrap.sh',
        stream=True,
    )
    if rc != 0:
        error("bootstrap.sh falló al preparar GN/Pigweed para Matter.")
        sys.exit(1)

    rc, out, err = run_bash(
        f'source {idf_q}/export.sh && export ESP_MATTER_PATH={matter_q} && '
        f'source {matter_q}/export.sh && command -v gn',
        capture=True,
    )
    gn_path = (out + err).strip().splitlines()
    if rc != 0 or not gn_path:
        error("GN sigue sin estar disponible tras bootstrap.")
        error("Abre una shell nueva y vuelve a ejecutar el script desde checkpoints.")
        sys.exit(1)

    success(f"GN disponible tras bootstrap: {gn_path[-1]}")

# ─────────────────────────────────────────────────
#  PASO 9 — Test final: build del ejemplo light
# ─────────────────────────────────────────────────
def test_matter_build():
    step_banner(9, TOTAL_STEPS, "Test final — build ejemplo Light (ESP32-C6)")

    idf_dir    = Path.home() / "esp" / "esp-idf"
    matter_dir = Path.home() / "esp" / "esp-matter"
    light_dir  = matter_dir / "examples" / "light"

    if is_done("test_matter_build"):
        success("Test de build ya completado (checkpoint).")
        return

    if not light_dir.exists():
        error(f"No se encontró el directorio de ejemplo: {light_dir}")
        sys.exit(1)

    build_dir = light_dir / "build"
    if build_dir.exists():
        info("Limpiando build previo de esp-matter/examples/light para evitar fallos de set-target…")
        try:
            shutil.rmtree(build_dir)
        except OSError as e:
            error(f"No se pudo limpiar el directorio build previo: {e}")
            sys.exit(1)

    info("Verificando disponibilidad de GN para Matter…")
    ensure_gn_available(idf_dir, matter_dir)

    info("Configurando target esp32c6…")
    idf_q    = shlex.quote(str(idf_dir))
    matter_q = shlex.quote(str(matter_dir))
    light_q  = shlex.quote(str(light_dir))
    # run() preserves os.environ; the sourced scripts set IDF_PATH/PATH in the subshell.
    rc, _, _ = run_bash(
        f'source {idf_q}/export.sh && export ESP_MATTER_PATH={matter_q} && source {matter_q}/export.sh && '
        f'cd {light_q} && idf.py set-target esp32c6',
        stream=True,
    )
    if rc != 0:
        error("idf.py set-target falló.")
        sys.exit(1)
    success("Target esp32c6 configurado.")

    info("Compilando ejemplo light (idf.py build) — puede tardar varios minutos…")
    print()
    rc, _, _ = run_bash(
        f'source {idf_q}/export.sh && export ESP_MATTER_PATH={matter_q} && source {matter_q}/export.sh && '
        f'cd {light_q} && idf.py build',
        stream=True,
    )
    if rc != 0:
        error("idf.py build falló. Revisa los errores anteriores.")
        sys.exit(1)
    success("Build del ejemplo light completado con éxito.")

    mark_done("test_matter_build")



def ensure_dialout_access():
    """Asegura acceso al grupo dialout para puertos serie en WSL.

    Retorna:
      - "ready": el usuario ya tenía acceso
      - "restart_required": se añadió al grupo, hay que reiniciar WSL
      - "fallback": no se pudo añadir; se intentará con sudo en flash
    """
    try:
        dialout_gid = grp.getgrnam("dialout").gr_gid
    except KeyError:
        warn("No existe el grupo 'dialout' en este sistema. Continuando…")
        return "ready"

    groups = os.getgroups()
    if dialout_gid in groups:
        success("Usuario actual ya pertenece a 'dialout'.")
        return "ready"

    warn("El usuario actual no pertenece al grupo 'dialout'.")
    info("Añadiendo usuario al grupo dialout para acceso serie sin sudo…")
    rc, _, _ = run(["sudo", "usermod", "-aG", "dialout", os.environ.get("USER", "")], stream=True)
    if rc != 0:
        warn("No se pudo añadir automáticamente al grupo dialout.")
        warn("Se intentará flashear con sudo como alternativa.")
        return "fallback"

    warn("Usuario añadido a 'dialout', pero requiere nueva sesión para aplicar cambios.")
    print(c(DIM, "  Acción manual requerida (una sola vez):"))
    print(c(DIM, "    1) En PowerShell: wsl --shutdown"))
    print(c(DIM, "    2) Reabrir Ubuntu/WSL"))
    print(c(DIM, "    3) Relanzar este script (retoma por checkpoints)"))
    return "restart_required"

# ─────────────────────────────────────────────────
#  PASO 10 — Flash guiado en placa ESP32-C6
# ─────────────────────────────────────────────────
def guided_flash_light_example():
    step_banner(10, TOTAL_STEPS, "Flash guiado en placa ESP32-C6")

    if is_done("guided_flash_light_example"):
        success("Flash guiado ya completado (checkpoint).")
        return

    idf_dir    = Path.home() / "esp" / "esp-idf"
    matter_dir = Path.home() / "esp" / "esp-matter"
    light_dir  = matter_dir / "examples" / "light"

    if not light_dir.exists():
        error(f"No se encontró el directorio de ejemplo: {light_dir}")
        sys.exit(1)

    info("Este paso requiere la placa conectada y adjuntada a WSL con usbipd.")
    dialout_status = ensure_dialout_access()
    if dialout_status == "restart_required":
        warn("Deteniendo instalación para aplicar cambios de grupo dialout.")
        warn("Reinicia WSL y vuelve a ejecutar install_diot.py; continuará desde checkpoints.")
        sys.exit(2)

    print(c(DIM, "  1) En PowerShell (Admin): usbipd list"))
    print(c(DIM, "  2) En PowerShell (Admin): usbipd bind --busid <BUSID>"))
    print(c(DIM, "  3) En PowerShell (Admin): usbipd attach --wsl --busid <BUSID>"))
    print(c(DIM, "  4) Vuelve aquí y pulsa ENTER para continuar"))
    print()

    resp = input(c(CYAN, "  Pulsa ENTER cuando la placa esté adjuntada a WSL (o escribe 's' para saltar): "))
    if resp.strip().lower() in ("s", "skip", "saltar"):
        warn("Flash omitido por el usuario. Puedes relanzar el script y retomará este paso.")
        return

    ports = sorted([str(p) for p in Path('/dev').glob('ttyACM*')] + [str(p) for p in Path('/dev').glob('ttyUSB*')])
    if ports:
        info("Puertos serie detectados en WSL:")
        for p in ports:
            rw = os.access(p, os.R_OK | os.W_OK)
            suffix = " (OK lectura/escritura)" if rw else " (sin permisos RW en esta sesión)"
            print(c(DIM, f"    • {p}{suffix}"))
        default_port = ports[0]
    else:
        warn("No se detectaron puertos /dev/ttyACM* ni /dev/ttyUSB*.")
        default_port = "/dev/ttyACM0"

    port_in = input(c(CYAN, f"  Puerto para flashear [{default_port}]: " )).strip()
    port = port_in or default_port

    idf_q = shlex.quote(str(idf_dir))
    matter_q = shlex.quote(str(matter_dir))
    light_q = shlex.quote(str(light_dir))
    port_q = shlex.quote(port)

    erase_resp = input(c(CYAN, "  ¿Borrar flash antes de flashear? (recomendado en laboratorio) [S/n]: " )).strip().lower()
    flash_action = "erase-flash flash" if erase_resp not in ("n", "no") else "flash"
    if flash_action == "erase-flash flash":
        warn("Se borrará toda la flash (incluye estado Matter comisionado) antes de grabar firmware.")

    info(f"Flasheando en {port} (acción: {flash_action})…")
    rc, _, _ = run_bash(
        f'source {idf_q}/export.sh && export ESP_MATTER_PATH={matter_q} && source {matter_q}/export.sh && '
        f'cd {light_q} && idf.py -p {port_q} {flash_action}',
        stream=True,
    )
    if rc != 0:
        warn("Flasheo sin sudo falló. Intentando con sudo (fallback por permisos de puerto)…")
        rc, _, _ = run_bash(
            f'source {idf_q}/export.sh && export ESP_MATTER_PATH={matter_q} && source {matter_q}/export.sh && '
            f'cd {light_q} && sudo idf.py -p {port_q} {flash_action}',
            stream=True,
        )
        if rc != 0:
            error("Flasheo falló incluso con sudo.")
            print(c(DIM, "  Verifica en PowerShell (Admin):"))
            print(c(DIM, "    usbipd list"))
            print(c(DIM, "    usbipd detach --busid <BUSID>"))
            print(c(DIM, "    usbipd attach --wsl --busid <BUSID>"))
            print(c(DIM, "  Verifica en WSL:"))
            print(c(DIM, "    ls -l /dev/ttyACM* /dev/ttyUSB*"))
            if dialout_status != "ready":
                print(c(DIM, "    (si añadiste dialout, haz wsl --shutdown y relanza script)"))
            sys.exit(1)

    success("Flash completado.")

    mon = input(c(CYAN, "  ¿Abrir monitor serie ahora? [S/n]: " )).strip().lower()
    if mon not in ("n", "no"):
        info("Abriendo monitor (salir con Ctrl+] o Ctrl+C)…")
        run_bash(
            f'source {idf_q}/export.sh && export ESP_MATTER_PATH={matter_q} && source {matter_q}/export.sh && '
            f'cd {light_q} && idf.py -p {port_q} monitor',
            stream=True,
        )

    mark_done("guided_flash_light_example")


# ─────────────────────────────────────────────────
#  PASO 11 — Configurar VS Code remoto (WSL)
# ─────────────────────────────────────────────────
def configure_vscode_remote_wsl():
    step_banner(11, TOTAL_STEPS, "Configurar VS Code remoto (WSL)")

    if is_done("configure_vscode_remote_wsl"):
        success("Configuración de VS Code remoto ya completada (checkpoint).")
        return

    idf_dir = Path.home() / "esp" / "esp-idf"
    tools_dir = Path.home() / ".espressif"

    info("Este paso deja VS Code listo para usar ESP-IDF en WSL en cualquier proyecto.")

    code_cmd = shutil.which("code")
    if code_cmd is None:
        warn("No se encontró el comando 'code' en WSL todavía.")
        print(c(DIM, "  Acción manual requerida:"))
        print(c(DIM, "    1) En Windows, abre VS Code"))
        print(c(DIM, "    2) Instala la extensión 'Remote - WSL' si falta"))
        print(c(DIM, "    3) Conéctate a Ubuntu/WSL"))
        print(c(DIM, "    4) En el remoto WSL, instala/reinstala 'Espressif IDF'"))
        input(c(CYAN, "  Cuando lo hayas hecho, pulsa ENTER para continuar: "))
        code_cmd = shutil.which("code")

    settings_path = Path.home() / ".vscode-server" / "data" / "Machine" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    settings = {}
    if settings_path.exists():
        raw = settings_path.read_text()
        if raw.strip():
            try:
                loaded = json.loads(raw)
                if isinstance(loaded, dict):
                    settings = loaded
                else:
                    warn("El settings.json remoto no es un objeto JSON. Se reemplazará por uno válido.")
            except json.JSONDecodeError:
                backup = settings_path.with_suffix(settings_path.suffix + ".bak")
                shutil.copy2(settings_path, backup)
                warn(f"settings.json no era JSON válido. Copia de seguridad: {backup}")

    settings["idf.currentSetup"] = str(idf_dir)
    custom_vars = settings.get("idf.customExtraVars")
    if not isinstance(custom_vars, dict):
        custom_vars = {}
    custom_vars["IDF_PATH"] = str(idf_dir)
    custom_vars["IDF_TOOLS_PATH"] = str(tools_dir)
    settings["idf.customExtraVars"] = custom_vars

    settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
    success(f"Configuración remota guardada en: {settings_path}")

    if code_cmd is not None:
        info("Intentando instalar la extensión ESP-IDF en el remoto WSL…")
        rc, _, _ = run([code_cmd, "--install-extension", "espressif.esp-idf-extension", "--force"], stream=True)
        if rc == 0:
            success("Extensión 'Espressif IDF' instalada/actualizada en WSL.")
        else:
            warn("No se pudo instalar automáticamente la extensión ESP-IDF por CLI.")
            warn("Instálala manualmente en Extensions (contexto WSL).")
    else:
        warn("Comando 'code' no disponible en WSL. Extensión ESP-IDF deberá instalarse manualmente.")

    print(c(DIM, "  Siguiente validación recomendada en VS Code (WSL):"))
    print(c(DIM, "    • ESP-IDF: Doctor Command"))
    print(c(DIM, "    • ESP-IDF: Open ESP-IDF Terminal"))

    mark_done("configure_vscode_remote_wsl")

# ─────────────────────────────────────────────────
#  Pantalla de bienvenida
# ─────────────────────────────────────────────────
def welcome():
    header(
        "DIOT — Instalador Automático\n"
        "usbipd · ESP-IDF v6.0.1 · ESP-Matter\n"
        "para Ubuntu 24+ en WSL 2"
    )
    print(c(DIM, "  Este script instalará automáticamente:"))
    print(c(DIM, "    • usbipd-win (Windows)"))
    print(c(DIM, "    • EIM — ESP-IDF Installation Manager"))
    print(c(DIM, "    • ESP-IDF v6.0.1 para ESP32-C6"))
    print(c(DIM, "    • ESP-Matter (Matter/Thread SDK)"))
    print()
    print(c(YELLOW, "  ⏱  Tiempo estimado total: 30–60 minutos"))
    print(c(YELLOW, "      (la descarga de Matter puede tardar bastante)"))
    print()

    if CHECKPOINT_FILE.exists():
        cp = load_checkpoints()
        done_count = sum(1 for v in cp.values() if v)
        if done_count > 0:
            print(c(GREEN, f"  ♻  Se encontraron {done_count} checkpoint(s) guardados."))
            resp = input(c(CYAN, "  ¿Continuar desde donde se dejó? [S/n]: ")).strip().lower()
            if resp in ("n", "no"):
                reset_checkpoints()
                info("Checkpoints borrados. Comenzando instalación desde cero.")
            else:
                info("Continuando desde el último checkpoint.")
    print()

# ─────────────────────────────────────────────────
#  Pantalla de finalización
# ─────────────────────────────────────────────────
def finish():
    idf_dir    = Path.home() / "esp" / "esp-idf"
    matter_dir = Path.home() / "esp" / "esp-matter"

    def box_line(text="", color=None):
        """Return a ║-padded line of exact BOX_WIDTH (ignoring ANSI codes)."""
        visible = re.sub(r"\033\[[^m]*m", "", text)
        pad = max(0, BOX_WIDTH - len(visible))
        colored_text = c(color, text) if color else text
        return c(CYAN, "║") + colored_text + " " * pad + c(CYAN, "║")

    idf_cmd    = f"    . {idf_dir}/export.sh"
    matter_cmd = f"    . {matter_dir}/export.sh"

    print()
    print(c(CYAN, "╔" + "═" * BOX_WIDTH + "╗"))
    print(box_line("  ✔  ¡Instalación completada con éxito!", GREEN + BOLD))
    print(c(CYAN, "╠" + "═" * BOX_WIDTH + "╣"))
    print(box_line("  Para activar el entorno ESP-IDF en una nueva shell:"))
    print(box_line(idf_cmd, CYAN))
    print(box_line("  Para activar ESP-Matter:"))
    print(box_line(matter_cmd, CYAN))
    print(box_line())
    print(box_line("  Conectar USB en WSL (PowerShell admin):"))
    print(box_line("    usbipd list"))
    print(box_line("    usbipd bind --busid <BUSID>"))
    print(box_line("    usbipd attach --wsl --busid <BUSID>"))
    print(c(CYAN, "╚" + "═" * BOX_WIDTH + "╝"))
    print()

# ─────────────────────────────────────────────────
#  Número total de pasos (para la barra de progreso)
# ─────────────────────────────────────────────────
TOTAL_STEPS = 11

# ─────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────
def main():
    welcome()
    request_sudo()

    try:
        check_wsl2()
        check_ubuntu_version()
        apt_update_upgrade()
        install_eim()
        install_usbipd()
        install_build_deps()
        install_esp_idf()
        install_esp_matter()
        test_matter_build()
        guided_flash_light_example()
        configure_vscode_remote_wsl()
    except KeyboardInterrupt:
        print()
        warn("Instalación interrumpida por el usuario.")
        warn(f"Los checkpoints se han guardado en {CHECKPOINT_FILE}")
        warn("Vuelve a ejecutar el script para continuar desde donde lo dejaste.")
        sys.exit(130)

    _sudo_alive.set()
    finish()


if __name__ == "__main__":
    main()
