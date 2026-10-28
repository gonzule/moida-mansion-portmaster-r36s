#!/bin/bash

XDG_DATA_HOME=${XDG_DATA_HOME:-$HOME/.local/share}

if [ -d "/opt/system/Tools/PortMaster/" ]; then
  controlfolder="/opt/system/Tools/PortMaster"
elif [ -d "/opt/tools/PortMaster/" ]; then
  controlfolder="/opt/tools/PortMaster"
elif [ -d "$XDG_DATA_HOME/PortMaster/" ]; then
  controlfolder="$XDG_DATA_HOME/PortMaster"
else
  controlfolder="/roms/ports/PortMaster"
fi

source $controlfolder/control.txt
[ -f "${controlfolder}/mod_${CFW_NAME}.txt" ] && source "${controlfolder}/mod_${CFW_NAME}.txt"
get_controls

GAMEDIR="/$directory/ports/moidamansion"
cd "$GAMEDIR"

> "$GAMEDIR/log.txt" && exec > >(tee "$GAMEDIR/log.txt") 2>&1

echo "--- Launching Moida Mansion ---"
echo "Date: $(date)"
echo "GAMEDIR: $GAMEDIR"
echo "CFW: $CFW_NAME"

# Ensure bin executables (Node.js engine) have execute permissions
chmod +x bin/* 2>/dev/null || true

PY_DIR="/tmp/pygame_runtime"
mount_success=0

try_mount() {
  local squash_file="$1"
  local py_ver="$2"
  if [ -f "$squash_file" ]; then
    echo "Attempting to mount: $squash_file -> $PY_DIR"
    $ESUDO mkdir -p "${PY_DIR}"
    if [[ "$PM_CAN_MOUNT" != "N" ]]; then
      $ESUDO umount "${PY_DIR}" 2>/dev/null || true
    fi
    if $ESUDO mount "$squash_file" "${PY_DIR}"; then
      if [ -f "${PY_DIR}/bin/python3" ] || [ -f "${PY_DIR}/bin/python" ]; then
        echo "Successfully mounted $squash_file (Python $py_ver)"
        mount_success=1
        ACTIVE_PY_VER="$py_ver"
        ACTIVE_SQUASH="$squash_file"
        return 0
      else
        echo "Mount succeeded but python binary not found inside image."
        $ESUDO umount "${PY_DIR}" 2>/dev/null || true
      fi
    else
      echo "Failed to mount $squash_file (wrong compression or kernel unsupported)."
    fi
  fi
  return 1
}

# 1. Try gzip squashfs first (universal compatibility on ArkOS / dArkOSen)
try_mount "$GAMEDIR/runtime/pygame-ce_2.5.6_python_3.12.8_gzip.squashfs" "3.12" || \
try_mount "$controlfolder/libs/pygame-ce_2.5.6_python_3.12.8_gzip.squashfs" "3.12" || \
# 2. Try standard xz squashfs
try_mount "$GAMEDIR/runtime/pygame-ce_2.5.6_python_3.12.8.squashfs" "3.12" || \
try_mount "$controlfolder/libs/pygame-ce_2.5.6_python_3.12.8.squashfs" "3.12" || \
try_mount "$controlfolder/libs/python_3.11.squashfs" "3.11"

# 3. If none mounted and harbourmaster exists, check harbourmaster
if [ "$mount_success" -eq 0 ] && [ -f "$controlfolder/harbourmaster" ]; then
  echo "Attempting Harbourmaster runtime check..."
  $ESUDO $controlfolder/harbourmaster --quiet --no-check runtime_check "python_3.11.squashfs"
  try_mount "$controlfolder/libs/python_3.11.squashfs" "3.11"
fi

if [ "$mount_success" -eq 1 ]; then
  if [ -f "${PY_DIR}/bin/activate" ]; then
    source "${PY_DIR}/bin/activate"
  fi
  export PYTHONHOME="${PY_DIR}"
  export PYTHONPATH="${PY_DIR}/lib/python${ACTIVE_PY_VER}:${PY_DIR}/lib/python${ACTIVE_PY_VER}/site-packages"
  export PATH="${PY_DIR}/bin:$PATH"
  export PYTHONPYCACHEPREFIX="${GAMEDIR}/.cache"

  if [ -f "${PY_DIR}/bin/python3" ]; then
    PYTHON="${PY_DIR}/bin/python3"
  elif [ -f "${PY_DIR}/bin/python" ]; then
    PYTHON="${PY_DIR}/bin/python"
  fi
else
  echo "Warning: No squashfs runtime mounted. Falling back to host system python3"
  PYTHON="python3"
fi

echo "Python executable: $PYTHON"
$PYTHON --version 2>&1

# Setup controller input & hotkeys
export SDL_GAMECONTROLLERCONFIG="$sdl_controllerconfig"
$ESUDO chmod 666 /dev/uinput 2>/dev/null || true
PY_BIN_NAME=$(basename "$PYTHON")
$GPTOKEYB "$PY_BIN_NAME" -c "./moidamansion.gptk" &

# Platform helper
pm_platform_helper "$PYTHON"

# Run game
$PYTHON main.py

# Cleanup
if [ "$mount_success" -eq 1 ]; then
  if [[ "$PM_CAN_MOUNT" != "N" ]]; then
    $ESUDO umount "${PY_DIR}" 2>/dev/null || true
  fi
fi

pm_finish
