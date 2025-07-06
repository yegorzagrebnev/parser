#!/bin/bash

REQUIRED_MAJOR=3
REQUIRED_MINOR=13
REQUIRED_PATCH=5
PY_EXE="python3"
VENV_DIR="venv"
REQUIREMENTS="requirements.txt"
APP_FILE="app.py"

if ! command -v $PY_EXE &> /dev/null; then
    echo "Python не найден. Установите Python $REQUIRED_MAJOR.$REQUIRED_MINOR.$REQUIRED_PATCH вручную:"
    echo "https://www.python.org/downloads/"
    exit 1
fi

CURRENT_VER=$($PY_EXE -c "import sys; print('.'.join(map(str, sys.version_info[:3])))")
MAJOR=$($PY_EXE -c "import sys; print(sys.version_info[0])")
MINOR=$($PY_EXE -c "import sys; print(sys.version_info[1])")

if [ "$MAJOR" -lt "$REQUIRED_MAJOR" ] || { [ "$MAJOR" -eq "$REQUIRED_MAJOR" ] && [ "$MINOR" -lt "$REQUIRED_MINOR" ]; }; then
    echo "Установлена устаревшая версия Python: $CURRENT_VER"
    echo "Установите Python $REQUIRED_MAJOR.$REQUIRED_MINOR.$REQUIRED_PATCH вручную:"
    echo "https://www.python.org/downloads/"
    exit 1
fi

echo "Найден Python $CURRENT_VER"

if [ ! -d "$VENV_DIR" ]; then
    echo "Создаю виртуальное окружение..."
    $PY_EXE -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
echo "Установка зависимостей..."
pip install --upgrade pip
pip install -r "$REQUIREMENTS"

echo "Запуск программы..."
streamlit run "$APP_FILE"

