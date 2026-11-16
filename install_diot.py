#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════╗
║         DIOT — Instalador Automático             ║
║  usbipd · ESP-IDF v6.0.1 · ESP-Matter           ║
╚══════════════════════════════════════════════════╝
Uso:
  python3 install_diot.py                 instalación completa, desatendida
  python3 install_diot.py --probar-placa  flashea una placa y comprueba que arranca
  python3 install_diot.py --desde-cero    ignora los checkpoints guardados
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
import argparse
from pathlib import Path

# ─────────────────────────────────────────────────
#  Colores ANSI
# ─────────────────────────────────────────────────
BOX_WIDTH = 54  # inner width (between ║ characters) for all UI boxes

WINGET_USBIPD_CMD = (
    "winget install --id dorssel.usbipd-win -e "
    "--accept-source-agreements --accept-package-agreements"
)

# Versión de ESP-Matter fijada: la misma con la que se han probado los
# proyectos de la asignatura. Cambiarla aquí si se actualiza el SDK.
ESP_MATTER_COMMIT = "a1ae4f06a8ab80c757c3389653a5b26e51d11c8a"
ESPRESSIF_USB_VID = "303a"

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
        "pkg-config",  # CRÍTICO para chip-tool: necesario para scripts de GN
        "libffi-dev", "libssl-dev", "libglib2.0-dev", "zlib1g-dev", "dfu-util",
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
    
    # POST-VALIDACIÓN: Verificar que pkg-config existe (crítico para chip-tool)
    info("Verificando que pkg-config se instaló correctamente…")
    rc_pkg, pkg_path, _ = run_bash("which pkg-config", capture=True)
    if rc_pkg != 0 or not pkg_path.strip():
        warn("pkg-config no se instaló o no está en PATH. Intentando instalación forzada…")
        rc_force, _, _ = run(
            ["sudo", "apt", "install", "-y", "--reinstall", "pkg-config"],
            capture=True
        )
        if rc_force == 0:
            success("pkg-config re-instalado.")
        else:
            error("No se pudo instalar pkg-config. Verificar conexión a internet y repositorios.")
            sys.exit(1)
    else:
        success(f"pkg-config disponible: {pkg_path.strip()}")

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
            info(f"Clonando ESP-IDF {idf_version} (solo esa versión, sin historial)…")
            print()
            rc, _, _ = run(
                ["git", "clone", "--progress",
                 "-b", idf_version, "--recursive",
                 "--depth", "1", "--shallow-submodules",
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
        info("Ejecutando install.sh esp32,esp32c6 (compatibilidad VS Code + C6; puede tardar)…")
        print()
        rc, _, _ = run(
            ["bash", "install.sh", "esp32,esp32c6"],
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
    step_banner(8, TOTAL_STEPS, "Instalar ESP-Matter (versión fijada, ~15 min)")

    esp_dir    = Path.home() / "esp"
    matter_dir = esp_dir / "esp-matter"
    idf_dir    = esp_dir / "esp-idf"

    matter_q = shlex.quote(str(matter_dir))
    chip_dir = matter_dir / "connectedhomeip" / "connectedhomeip"

    if is_done("clone_esp_matter"):
        success("ESP-Matter ya clonado (checkpoint).")
    else:
        esp_dir.mkdir(parents=True, exist_ok=True)
        if (matter_dir / ".git").exists():
            warn(f"{matter_dir} ya existe. Se usará tal cual (no se cambia de versión).")
        else:
            info(f"Descargando ESP-Matter {ESP_MATTER_COMMIT[:8]} (solo esa versión, sin historial)…")
            matter_dir.mkdir(parents=True, exist_ok=True)
            rc, _, _ = run_bash(
                f'cd {matter_q} && git init -q && '
                f'git remote add origin https://github.com/espressif/esp-matter.git && '
                f'git fetch --progress --depth 1 origin {ESP_MATTER_COMMIT} && '
                f'git checkout -q FETCH_HEAD',
                stream=True,
            )
            if rc != 0:
                error("No se pudo descargar ESP-Matter.")
                sys.exit(1)
        info("Descargando connectedhomeip (submódulo principal, sin historial)…")
        rc, _, _ = run(["git", "submodule", "update", "--init", "--depth", "1"],
                       cwd=str(matter_dir), stream=True)
        if rc != 0:
            error("git submodule update falló en ESP-Matter.")
            sys.exit(1)
        # Solo los submódulos que necesita ESP32 (y Linux para las herramientas
        # de build). Es lo que recomienda Espressif y ahorra decenas de GB.
        info("Descargando submódulos de connectedhomeip solo para esp32 y linux…")
        rc, _, _ = run(
            ["python3", "scripts/checkout_submodules.py",
             "--platform", "esp32", "linux", "--shallow"],
            cwd=str(chip_dir), stream=True,
        )
        if rc != 0:
            error("checkout_submodules.py falló.")
            sys.exit(1)
        success("ESP-Matter descargado.")
        mark_done("clone_esp_matter")

    if not chip_dir.exists():
        error(f"No existe {chip_dir}. Borra {matter_dir}, ejecuta con --desde-cero y reintenta.")
        sys.exit(1)

    if is_done("export_esp_matter"):
        success("ESP-Matter ya inicializado (checkpoint).")
    else:
        # install.sh hace el bootstrap de Pigweed (gn, zap…). --no-host-tool
        # evita compilar chip-tool, que no se usa en la asignatura.
        info("Ejecutando install.sh --no-host-tool de ESP-Matter (bootstrap; varios minutos)…")
        print()
        idf_q = shlex.quote(str(idf_dir))
        rc, _, _ = run_bash(
            f'source {idf_q}/export.sh && cd {matter_q} && ./install.sh --no-host-tool',
            stream=True,
        )
        if rc != 0:
            error("install.sh de ESP-Matter falló.")
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
#  --probar-placa — Flashear y comprobar una placa ESP32-C6
# ─────────────────────────────────────────────────
SERIAL_CHECK_PY = r"""
import sys, time, serial
port, timeout = sys.argv[1], float(sys.argv[2])
ser = serial.Serial()
ser.port, ser.baudrate, ser.timeout = port, 115200, 0.2
ser.dtr = False
ser.rts = False
ser.open()
ser.rts = True; time.sleep(0.2); ser.rts = False   # reset (EN)
buf, t0 = b"", time.time()
while time.time() - t0 < timeout:
    buf += ser.read(4096)
    text = buf.decode("utf-8", "replace")
    if "SetupQRCode" in text or "Manual pairing code" in text:
        sys.stdout.write(text); print("\n__DIOT_OK__"); sys.exit(0)
    if "Guru Meditation" in text or text.count("rst:0x") > 3:
        sys.stdout.write(text); print("\n__DIOT_CRASH__"); sys.exit(3)
sys.stdout.write(buf.decode("utf-8", "replace")); print("\n__DIOT_TIMEOUT__"); sys.exit(4)
"""


def _serial_ports():
    return sorted(str(p) for p in list(Path("/dev").glob("ttyACM*")) + list(Path("/dev").glob("ttyUSB*")))


def _find_usbipd():
    for cand in ("usbipd.exe", "/mnt/c/Program Files/usbipd-win/usbipd.exe"):
        path = shutil.which(cand) or (cand if Path(cand).exists() else None)
        if path:
            return path
    return None


def _attach_espressif_board():
    """Intenta pasar la placa de Windows a WSL. Devuelve True si hay puerto serie."""
    usbipd = _find_usbipd()
    if usbipd is None:
        warn("No encuentro usbipd.exe desde WSL.")
        return False
    rc, out, _ = run([usbipd, "list"], capture=True)
    lines = [l for l in out.splitlines() if ESPRESSIF_USB_VID in l.lower()]
    if rc != 0 or not lines:
        warn("Windows no ve ninguna placa Espressif. ¿Está enchufada? Prueba otro cable/puerto USB.")
        return False
    line = lines[0]
    busid = line.split()[0]
    info(f"Placa encontrada en Windows: {line.strip()}")
    if "not shared" in line.lower():
        error("La placa todavía no está compartida con WSL (se hace una sola vez por PC).")
        print(c(BOLD, "  Abre PowerShell COMO ADMINISTRADOR y ejecuta:"))
        print(c(CYAN, f"      usbipd bind --busid {busid}"))
        print(c(BOLD, "  Luego vuelve a lanzar:  python3 install_diot.py --probar-placa"))
        return False
    if "attached" not in line.lower():
        info(f"Conectando la placa a WSL (usbipd attach --wsl --busid {busid})…")
        run([usbipd, "attach", "--wsl", "--busid", busid], capture=True)
    for _ in range(20):
        if _serial_ports():
            return True
        time.sleep(0.5)
    return False


def probar_placa():
    header("DIOT — Prueba de placa ESP32-C6")
    idf_dir    = Path.home() / "esp" / "esp-idf"
    matter_dir = Path.home() / "esp" / "esp-matter"
    light_dir  = matter_dir / "examples" / "light"

    if not (light_dir / "build" / "light.bin").exists():
        error("No está compilado el ejemplo light. Ejecuta antes la instalación completa:")
        print(c(CYAN, "      python3 install_diot.py"))
        sys.exit(1)

    try:
        dialout_gid = grp.getgrnam("dialout").gr_gid
        if dialout_gid not in os.getgroups():
            ensure_dialout_access()
            error("Cierra Ubuntu, en PowerShell ejecuta 'wsl --shutdown', reabre y repite.")
            sys.exit(2)
    except KeyError:
        pass

    if not _serial_ports():
        info("No hay puerto serie en WSL todavía; intento conectar la placa con usbipd…")
        if not _attach_espressif_board():
            print()
            print(c(RED + BOLD, "  ✘  PLACA NO DETECTADA"))
            sys.exit(1)
    port = _serial_ports()[0]
    success(f"Puerto serie: {port}")

    idf_q, matter_q, light_q, port_q = (shlex.quote(str(x)) for x in (idf_dir, matter_dir, light_dir, port))
    env_cmd = f'source {idf_q}/export.sh >/dev/null && export ESP_MATTER_PATH={matter_q} && source {matter_q}/export.sh >/dev/null'

    info("Borrando la flash y grabando el ejemplo light (≈1 min)…")
    rc, out, _ = run_bash(f'{env_cmd} && cd {light_q} && idf.py -p {port_q} erase-flash flash', stream=True)
    if rc != 0:
        print()
        print(c(RED + BOLD, "  ✘  FALLO AL FLASHEAR"))
        print(c(DIM, "  Desenchufa y vuelve a enchufar la placa y repite. Si sigue fallando,"))
        print(c(DIM, "  mantén pulsado BOOT, pulsa RST, suelta BOOT y repite."))
        sys.exit(1)
    success("Flash grabada.")

    info("Reiniciando la placa y esperando a que Matter arranque (máx. 30 s)…")
    rc, out, _ = run_bash(f'{env_cmd} && python -c {shlex.quote(SERIAL_CHECK_PY)} {port_q} 30', capture=True)
    log = out.strip().splitlines()
    for l in [l for l in log if "SetupQRCode" in l or "Manual pairing" in l]:
        print(c(DIM, f"    {l.strip()}"))
    print()
    if "__DIOT_OK__" in out:
        print(c(GREEN + BOLD, "  ✔  PLACA OK — compila, flashea y arranca Matter en este PC"))
        sys.exit(0)
    for l in log[-15:]:
        print(c(DIM, f"    {l}"))
    if "__DIOT_CRASH__" in out:
        print(c(RED + BOLD, "  ✘  LA PLACA SE REINICIA EN BUCLE (ver log arriba)"))
    else:
        print(c(RED + BOLD, "  ✘  LA PLACA NO RESPONDE POR EL PUERTO SERIE (ver log arriba)"))
    sys.exit(1)


# ─────────────────────────────────────────────────
#  PASO 10 — Configurar VS Code remoto (WSL)
# ─────────────────────────────────────────────────
def configure_vscode_remote_wsl():
    step_banner(10, TOTAL_STEPS, "Configurar VS Code remoto (WSL)")

    if is_done("configure_vscode_remote_wsl"):
        warn("Paso 11 ya estaba marcado, pero se revalidará la configuración VS Code para aplicar correcciones.")

    idf_dir = Path.home() / "esp" / "esp-idf"
    tools_dir = Path.home() / ".espressif"

    info("Este paso deja VS Code listo para usar ESP-IDF en WSL en cualquier proyecto.")

    python_env_candidates = sorted((tools_dir / "python_env").glob("*/bin/python"))
    idf_python_env_path = os.environ.get("IDF_PYTHON_ENV_PATH", "")
    if not idf_python_env_path and python_env_candidates:
        # Prefer envs matching idf6.0 if available; otherwise first detected env.
        preferred = [p for p in python_env_candidates if "idf6.0" in str(p)]
        chosen_python = preferred[0] if preferred else python_env_candidates[0]
        idf_python_env_path = str(chosen_python.parent)

    xtensa_tools_dir = tools_dir / "tools" / "xtensa-esp-elf"
    ulp_tools_dir = tools_dir / "tools" / "esp32ulp-elf"
    if not xtensa_tools_dir.exists() or not ulp_tools_dir.exists():
        warn("Faltan toolchains xtensa/ulp que la extensión ESP-IDF suele validar.")
        info("Instalando toolchains adicionales con install.sh esp32 (solo una vez)…")
        rc, _, _ = run(["bash", "install.sh", "esp32"], cwd=str(idf_dir), stream=True)
        if rc != 0:
            warn("No se pudieron instalar automáticamente los toolchains extra.")
            warn("La extensión podría seguir mostrando errores de setup en VS Code.")
        else:
            success("Toolchains extra (esp32/xtensa/ulp) instalados para compatibilidad de extensión.")

    code_cmd = shutil.which("code")
    if code_cmd is None:
        warn("No se encontró el comando 'code' en WSL todavía.")
        print(c(DIM, "  Se configura igualmente. Para terminar (una vez, cuando quieras):"))
        print(c(DIM, "    1) En Windows, abre VS Code e instala la extensión 'WSL'"))
        print(c(DIM, "    2) Conéctate a Ubuntu/WSL"))
        print(c(DIM, "    3) En el remoto WSL, instala la extensión 'Espressif IDF'"))

    bashrc_path = Path.home() / ".bashrc"
    export_lines = [
        f"export IDF_PATH={idf_dir}",
        f"export IDF_TOOLS_PATH={tools_dir}",
        f"export IDF_PYTHON_ENV_PATH={idf_python_env_path}" if idf_python_env_path else "",
        f"export ESP_MATTER_PATH={Path.home() / 'esp' / 'esp-matter'}",
    ]
    existing_bashrc = bashrc_path.read_text() if bashrc_path.exists() else ""
    appended = False
    for line in export_lines:
        if not line:
            continue
        if line not in existing_bashrc:
            existing_bashrc += ("\n" if existing_bashrc and not existing_bashrc.endswith("\n") else "") + line + "\n"
            appended = True

    auto_load_begin = "# >>> DIOT ESP-IDF/Matter auto-load >>>"
    auto_load_end = "# <<< DIOT ESP-IDF/Matter auto-load <<<"
    auto_load_block = (
        f"{auto_load_begin}\n"
        'if [ -f "$IDF_PATH/export.sh" ]; then\n'
        '  . "$IDF_PATH/export.sh" >/dev/null 2>&1\n'
        'fi\n'
        'if [ -f "$ESP_MATTER_PATH/export.sh" ]; then\n'
        '  . "$ESP_MATTER_PATH/export.sh" >/dev/null 2>&1\n'
        'fi\n'
        f"{auto_load_end}\n"
    )

    if auto_load_begin in existing_bashrc and auto_load_end in existing_bashrc:
        block_start = existing_bashrc.index(auto_load_begin)
        block_end = existing_bashrc.index(auto_load_end, block_start) + len(auto_load_end)
        if block_end < len(existing_bashrc) and existing_bashrc[block_end:block_end + 1] == "\n":
            block_end += 1
        existing_bashrc = existing_bashrc[:block_start] + auto_load_block + existing_bashrc[block_end:]
        appended = True
    elif auto_load_begin not in existing_bashrc:
        existing_bashrc += ("\n" if existing_bashrc and not existing_bashrc.endswith("\n") else "") + auto_load_block
        appended = True

    if appended:
        bashrc_path.write_text(existing_bashrc)
        success("Variables y auto-carga IDF/Matter añadidas a ~/.bashrc para nuevas terminales WSL.")
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
    if idf_python_env_path:
        custom_vars["IDF_PYTHON_ENV_PATH"] = idf_python_env_path
    custom_vars["IDF_TARGET"] = "esp32c6"
    settings["idf.customExtraVars"] = custom_vars

    serial_ports = sorted([str(p) for p in Path('/dev').glob('ttyACM*')] + [str(p) for p in Path('/dev').glob('ttyUSB*')])
    default_port = serial_ports[0] if serial_ports else "/dev/ttyACM0"
    settings["idf.port"] = default_port
    settings["idf.monitorPort"] = default_port
    settings["idf.flashType"] = "UART"

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
#  PASO 11 — Instalar Matrix MCU (Toolchain ARM para STM32)
# ─────────────────────────────────────────────────
def install_matrix_mcu():
    step_banner(11, TOTAL_STEPS, "Matrix MCU (SDG2) — Toolchain ARM para STM32")

    if is_done("install_matrix_mcu"):
        success("Matrix MCU ya instalado (checkpoint).")
        return

    arm_gcc = Path("/opt/MatrixMCU/bin/arm-none-eabi-gcc")
    if arm_gcc.exists() and run([str(arm_gcc), "--version"], capture=True)[0] == 0:
        success("Toolchain ARM de MatrixMCU ya instalado en /opt/MatrixMCU.")
        mark_done("install_matrix_mcu")
        return

    # Detectar versión de Ubuntu
    os_info = Path("/etc/os-release").read_text() if Path("/etc/os-release").exists() else ""
    ubuntu_major = 24  # default
    ver_match = re.search(r'^VERSION_ID="?([^"\n]+)"?', os_info, re.M)
    if ver_match:
        try:
            ubuntu_major = int(ver_match.group(1).split(".")[0])
        except (ValueError, IndexError):
            pass

    info(f"Detectada Ubuntu {ubuntu_major}.")

    matrix_mcu_dir = Path.home() / "install-MatrixMCU"

    if matrix_mcu_dir.exists():
        info(f"Repositorio Matrix MCU ya existe en: {matrix_mcu_dir}")
    else:
        info(f"Clonando Matrix MCU en: {matrix_mcu_dir}")
        print()
        rc, _, _ = run(
            ["git", "clone", "--progress",
             "--depth", "1",
             "https://github.com/sdg2DieUpm/install-MatrixMCU.git",
             str(matrix_mcu_dir)],
            stream=True
        )
        if rc != 0:
            error("No se pudo clonar Matrix MCU.")
            sys.exit(1)
        success("Matrix MCU clonado.")

    # Determinar script a ejecutar
    script_name = f"ubuntu{ubuntu_major}.sh"
    script_path = matrix_mcu_dir / script_name

    if not script_path.exists():
        error(f"Script {script_name} no existe en {matrix_mcu_dir}")
        error(f"Matrix MCU disponibles para Ubuntu 22 y 24; detectaste Ubuntu {ubuntu_major}.")
        sys.exit(1)

    # Ejecutar script
    info(f"Ejecutando {script_name} (instalará arm-none-eabi-gcc y herramientas)…")
    info("Esto puede tardar 10-20 minutos…")
    print()
    
    # El script añade /opt/MatrixMCU/bin al PATH en ~/.bashrc, pero ese
    # cambio no se ve en esta shell no interactiva: se verifica por ruta.
    matrix_mcu_q = shlex.quote(str(matrix_mcu_dir))
    rc, out_combined, err_combined = run_bash(
        f'cd {matrix_mcu_q} && bash ./{script_name} && '
        f'/opt/MatrixMCU/bin/arm-none-eabi-gcc --version 2>&1',
        stream=True,
    )

    if rc != 0:
        error("Instalación de Matrix MCU o verificación falló.")
        warn(f"Intenta manualmente: cd {matrix_mcu_dir} && bash {script_name}")
        if out_combined or err_combined:
            print(c(DIM, (out_combined + err_combined)[-500:]))  # Mostrar últimas 500 chars
        sys.exit(1)
    
    success("Matrix MCU instalado correctamente.")

    # Mostrar versión verificada
    info("Verificado arm-none-eabi-gcc:")
    version_lines = (out_combined + err_combined).strip().splitlines()
    for line in version_lines[-3:]:
        if line.strip():
            success(f"  {line}")

    mark_done("install_matrix_mcu")

# ─────────────────────────────────────────────────
#  PASO 12 — Compilar proyecto template de MatrixMCU
# ─────────────────────────────────────────────────
def test_matrix_mcu_build():
    step_banner(12, TOTAL_STEPS, "Test compilación Matrix MCU — Proyecto template")

    if is_done("test_matrix_mcu_build"):
        success("Test de compilación Matrix MCU ya completado (checkpoint).")
        return

    matrix_mcu_dir = Path.home() / "MatrixMCU"
    template_dir = matrix_mcu_dir / "projects" / "project_template"

    # Si MatrixMCU no existe, clonarlo
    if not matrix_mcu_dir.exists():
        info(f"Clonando MatrixMCU en: {matrix_mcu_dir}")
        print()
        rc, _, _ = run(
            ["git", "clone", "--progress", "--recursive",
             "--depth", "1", "--shallow-submodules",
             "https://github.com/sdg2DieUpm/MatrixMCU.git",
             str(matrix_mcu_dir)],
            stream=True
        )
        if rc != 0:
            error("No se pudo clonar MatrixMCU.")
            sys.exit(1)
        success("MatrixMCU clonado recursivamente.")
    else:
        info(f"MatrixMCU ya existe en: {matrix_mcu_dir}")

    # Verificar que el proyecto template existe
    if not template_dir.exists():
        error(f"No se encontró proyecto template en: {template_dir}")
        sys.exit(1)

    info(f"Compilando proyecto template de MatrixMCU…")
    info("Ubicación: " + str(template_dir))
    print()

    template_q = shlex.quote(str(template_dir))
    
    # Compilar: mkdir build, cd build, cmake -G Ninja .., ninja -v
    rc, out, err = run_bash(
        f'export PATH=/opt/MatrixMCU/bin:$PATH && '
        f'cd {template_q} && '
        f'rm -rf build && '
        f'mkdir -p build && '
        f'cd build && '
        f'cmake -G Ninja .. 2>&1 && '
        f'ninja -v',
        stream=True,
        capture=True
    )

    if rc != 0:
        error("Compilación del proyecto template de MatrixMCU falló.")
        warn("Output de cmake/ninja:")
        error_lines = (out + err).strip().splitlines()[-20:]
        for line in error_lines:
            if line.strip():
                print(c(YELLOW, f"  {line}"))
        print()
        sys.exit(1)

    # Verificar que el binario fue creado
    # MatrixMCU genera .elf en: bin/stm32f446re/Debug/ (no en build/)
    build_dir = template_dir / "build"
    bin_dir = template_dir / "bin"
    
    # Buscar .elf en todo el directorio del template
    elf_files = list(template_dir.glob("**/*.elf"))

    if not elf_files:
        # No se encontró .elf
        warn("⚠ Compilación ejecutó sin errores (rc=0) pero no se encontró .elf")
        warn("Directorios esperados:")
        print(c(DIM, f"    {build_dir}"))
        print(c(DIM, f"    {bin_dir}"))
        warn(f"\nArchivos generados en {build_dir}:")
        for f in sorted(build_dir.rglob("*"))[:15]:
            if f.is_file():
                print(c(DIM, f"    {f.relative_to(build_dir)}"))
        
        error("No se pudo verificar compilación (no hay .elf)")
        sys.exit(1)
    else:
        success(f"✓ Binarios compilados exitosamente:")
        for elf in elf_files:
            success(f"  • {elf.relative_to(template_dir)}")
        
        success("Test de compilación Matrix MCU completado con éxito.")
    
    mark_done("test_matrix_mcu_build")

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
    print(c(DIM, "    • Configuración VS Code remoto WSL"))
    print(c(DIM, "    • Matrix MCU (Toolchain STM32, para SDG2)"))
    print(c(DIM, "    • Test compilación proyecto template MatrixMCU"))
    print()
    print(c(YELLOW, "  ⏱  Tiempo estimado: 30–50 min. No hace falta estar delante."))
    print(c(YELLOW, "      Al terminar: python3 install_diot.py --probar-placa"))
    print()

    if CHECKPOINT_FILE.exists():
        done_count = sum(1 for v in load_checkpoints().values() if v)
        if done_count > 0:
            print(c(GREEN, f"  ♻  {done_count} paso(s) ya hechos: se continúa desde ahí."))
            print(c(DIM, "     (para empezar de cero: --desde-cero)"))
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
    print(box_line())
    print(box_line("  Comprobar una placa (enchufada al PC):"))
    print(box_line("    python3 install_diot.py --probar-placa", CYAN))
    print(c(CYAN, "╚" + "═" * BOX_WIDTH + "╝"))
    print()

# ─────────────────────────────────────────────────
#  Número total de pasos (para la barra de progreso)
# ─────────────────────────────────────────────────
TOTAL_STEPS = 12

# ─────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Instalador del entorno DIOT (ESP-IDF + ESP-Matter + MatrixMCU) en WSL.")
    parser.add_argument("--probar-placa", action="store_true",
                        help="flashea el ejemplo light en la placa conectada y comprueba que arranca")
    parser.add_argument("--desde-cero", action="store_true",
                        help="borra los checkpoints y repite todos los pasos")
    args = parser.parse_args()

    if args.probar_placa:
        probar_placa()
        return
    if args.desde_cero:
        reset_checkpoints()

    welcome()
    request_sudo()

    try:
        check_wsl2()
        check_ubuntu_version()
        apt_update_upgrade()
        install_eim()
        install_usbipd()
        install_build_deps()
        dialout_status = ensure_dialout_access()
        install_esp_idf()
        install_esp_matter()
        test_matter_build()
        configure_vscode_remote_wsl()
        install_matrix_mcu()
        test_matrix_mcu_build()
    except KeyboardInterrupt:
        print()
        warn("Instalación interrumpida por el usuario.")
        warn(f"Los checkpoints se han guardado en {CHECKPOINT_FILE}")
        warn("Vuelve a ejecutar el script para continuar desde donde lo dejaste.")
        sys.exit(130)

    _sudo_alive.set()
    finish()
    if dialout_status == "restart_required":
        warn("Antes de --probar-placa: cierra Ubuntu, 'wsl --shutdown' en PowerShell y reabre.")


if __name__ == "__main__":
    main()
