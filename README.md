# install-diot

Instalador automático del entorno de laboratorio de **DIOT** (y de **SDG2**) en
**Ubuntu 24+ / WSL 2**.

Instala de una vez, **sin hacer preguntas** (se puede lanzar y dejar solo):

- **usbipd-win**: para pasar la placa USB de Windows a WSL.
- **EIM**: ESP-IDF Installation Manager.
- **ESP-IDF v6.0.1**: framework de Espressif para ESP32-C6.
- **ESP-Matter**: SDK de Matter, en la versión fijada con la que se han probado los
  proyectos de la asignatura.
- **Configuración de VS Code remoto (WSL)** para ESP-IDF.
- **MatrixMCU**: toolchain ARM para STM32 (SDG2), y compilación de su proyecto plantilla.

Para que sea rápido, todo se descarga **sin historial de git**, ESP-Matter solo con los
submódulos de ESP32 y Linux (no los de otros fabricantes), y no se compila `chip-tool`.

## Requisitos previos

| Requisito | Mínimo |
|-----------|--------|
| Windows | 10 / 11 con WSL 2 activo |
| Distribución WSL | Ubuntu 24.04 LTS |
| RAM libre | 4 GB recomendado |
| Espacio en disco | ~15 GB |

## Uso (en cada PC)

```bash
git clone https://github.com/die-diot/install-diot.git ~/install-diot
cd ~/install-diot
python3 install_diot.py
```

Pide la contraseña de `sudo` al principio y ya no pregunta nada más. Tarda unos
30–50 min según la red.

Si se corta o se cierra la ventana, se vuelve a lanzar el mismo comando y continúa
donde se quedó (guarda *checkpoints* en `~/.diot_install_checkpoints.json`). Para
repetirlo todo: `python3 install_diot.py --desde-cero`.

## Comprobar que el flasheo funciona (con una placa)

No hace falta en todos los PCs: con 2 o 3 basta, porque todos quedan iguales. Se usa
**una placa y un cable** que se van llevando de un PC a otro:

1. Enchufa la ESP32-C6 por el conector marcado como **USB** (no el UART).
2. Solo la primera vez en cada PC, en **PowerShell como administrador**:

   ```powershell
   usbipd list                    # busca "USB JTAG/serial debug unit"
   usbipd bind --busid <BUSID>
   ```

   Si se te olvida, el paso 3 te dice exactamente qué escribir.
3. En Ubuntu:

   ```bash
   python3 ~/install-diot/install_diot.py --probar-placa
   ```

El script conecta la placa a WSL, borra la flash, graba el ejemplo `light` de Matter,
reinicia la placa y lee su arranque. Termina con uno de estos mensajes:

| Mensaje | Qué significa |
|---------|---------------|
| `✔ PLACA OK` | Este PC compila, flashea y la placa arranca Matter. Listo. |
| `✘ PLACA NO DETECTADA` | Windows no ve la placa o falta el `usbipd bind`. Revisa cable y puerto. |
| `✘ FALLO AL FLASHEAR` | Desenchufa y enchufa. Si persiste: mantén BOOT, pulsa RST, suelta BOOT y repite. |
| `✘ LA PLACA SE REINICIA EN BUCLE` / `NO RESPONDE` | Prueba con otra placa para descartar el hardware. |

La flash queda borrada y con el ejemplo `light`, así que la placa vale tal cual para el
siguiente PC o para los alumnos.

## Pasos de instalación

| Paso | Descripción |
|------|-------------|
| 1 | Verificar que la distro WSL está en versión 2 |
| 2 | Verificar Ubuntu 24+ |
| 3 | `apt update && apt upgrade` |
| 4 | Instalar EIM (gestor de ESP-IDF) |
| 5 | Instalar usbipd-win desde Windows |
| 6 | Instalar dependencias de build y dar acceso al puerto serie (`dialout`) |
| 7 | Descargar e instalar ESP-IDF v6.0.1 |
| 8 | Descargar ESP-Matter (versión fijada) y hacer su bootstrap |
| 9 | Compilar el ejemplo `light` de ESP-Matter para ESP32-C6 |
| 10 | Configurar VS Code remoto (WSL) y la auto-carga del entorno en `~/.bashrc` |
| 11 | Instalar MatrixMCU (toolchain ARM en `/opt/MatrixMCU`) desde `~/install-MatrixMCU` |
| 12 | Compilar el proyecto plantilla de MatrixMCU (`~/MatrixMCU`) |

## Rutas que deja instaladas

| Qué | Dónde |
|-----|-------|
| ESP-IDF | `~/esp/esp-idf` |
| ESP-Matter | `~/esp/esp-matter` (variable `ESP_MATTER_PATH`) |
| Toolchains de Espressif | `~/.espressif` |
| MatrixMCU | `~/install-MatrixMCU`, `~/MatrixMCU`, `/opt/MatrixMCU/bin` |

Las terminales nuevas de WSL cargan ESP-IDF y ESP-Matter automáticamente.

## Actualizar la versión de ESP-Matter

Está fijada en la constante `ESP_MATTER_COMMIT` al principio de `install_diot.py`.
Si se cambia, hay que borrar `~/esp/esp-matter` en los PCs y relanzar el instalador.
