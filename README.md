# install-diot

Instalador automático para el entorno de desarrollo DIOT en **Ubuntu 24+ / WSL 2**.

Instala en un solo paso:

- **usbipd-win** — para pasar dispositivos USB desde Windows a WSL
- **EIM** — ESP-IDF Installation Manager
- **ESP-IDF v6.0.1** — framework de Espressif para ESP32-C6
- **ESP-Matter** — SDK de Matter/Thread de Espressif

## Requisitos previos

| Requisito | Mínimo |
|-----------|--------|
| Windows   | 10 / 11 con WSL 2 activo |
| Distribución WSL | Ubuntu 24.04 LTS |
| RAM libre | 4 GB recomendado |
| Espacio en disco | ~10 GB (Matter + toolchains) |
| Python | 3.8+ (incluido en Ubuntu 24) |

## Uso

```bash
# Dar permisos de ejecución (solo la primera vez)
chmod +x install_diot.py

# Ejecutar
./install_diot.py
# o bien
python3 install_diot.py
```

El instalador pedirá la contraseña `sudo` una sola vez al inicio y la mantendrá activa durante todo el proceso.

## Características

- ✅ **Checkpoints automáticos** — si la instalación se interrumpe, puedes reanudarla exactamente donde se quedó.
- 📊 **Barra de progreso** — muestra el porcentaje de descarga/compilación en tiempo real.
- 🎨 **Salida con color** — cada paso es fácil de identificar.
- 🔁 **Idempotente** — es seguro ejecutarlo varias veces.

## Pasos de instalación

| Paso | Descripción |
|------|-------------|
| 1 | Verificar que la distro WSL está en versión 2 |
| 2 | Verificar Ubuntu 24+ |
| 3 | `apt update && apt upgrade` |
| 4 | Instalar EIM (gestor de ESP-IDF) |
| 5 | Instalar usbipd-win desde Windows |
| 6 | Instalar dependencias de build en Ubuntu |
| 7 | Clonar e instalar ESP-IDF v6.0.1 |
| 8 | Clonar e inicializar ESP-Matter |
| 9 | Build de prueba final (ejemplo `light` para ESP32-C6) |

## Conectar el ESP32-C6 por USB

Una vez instalado, abre **PowerShell como administrador** y ejecuta:

```powershell
usbipd list                          # localiza el BUSID de tu dispositivo
usbipd bind --busid <BUSID>          # comparte el dispositivo con WSL
usbipd attach --wsl --busid <BUSID>  # conecta el dispositivo a WSL
```

En WSL podrás ver el dispositivo con `ls /dev/ttyACM*` o `ls /dev/ttyUSB*`.

## Activar el entorno tras la instalación

Añade estas líneas a tu `~/.bashrc` (o ejecútalas manualmente en cada sesión):

```bash
. ~/esp/esp-idf/export.sh
. ~/esp/esp-matter/export.sh
```
