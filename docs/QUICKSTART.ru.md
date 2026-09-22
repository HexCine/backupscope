# BackupScope: первый запуск

Сравните Docker mounts со списком файлов снимка restic: найдите отсутствующие пути и устаревшие данные.

**[Скачать визуальное руководство EN/RU](https://github.com/HexCine/backupscope/releases/download/v0.2.1/start.html)** — сохраните HTML и откройте в браузере. Код не отправляется на сервер.

## 1. Установка

Скачайте [backupscope-0.2.1-source.zip](https://github.com/HexCine/backupscope/releases/download/v0.2.1/backupscope-0.2.1-source.zip), распакуйте и откройте терминал в корне проекта.
Требуется Python 3.11+. Создайте venv: `python -m venv .venv`. Активируйте `.venv/Scripts/Activate.ps1` (PowerShell) или `source .venv/bin/activate` (macOS/Linux). Либо используйте путь к Python окружения вместо `python`.

```sh
python -m pip install .
```

## 2. Учебная проблема

```sh
python -m backupscope check --inventory examples/inventory.json --snapshot examples/missing.jsonl --policy examples/policy.json --at 2026-09-22T13:00:00Z
```

Неполная копия возвращает 1: нет документов, SQL-дамп старый. Полный пример возвращает 0. --at фиксирует время только для этих примеров.

## 3. Контрольный пример

```sh
python -m backupscope check --inventory examples/inventory.json --snapshot examples/present.jsonl --policy examples/policy.json --at 2026-09-22T13:00:00Z
```

Ожидается код 0. При коде 2 проверьте входные данные: полного вывода нет.
Примеры синтетические. Для повторного создания demo выберите новую папку.

## Свои данные

Проверьте policy.local.json: точный host, теги и пути в снимке. Затем выполните verify с --latest и существующей конфигурацией restic. Полная команда и HTML-отчёт — в README.

```sh
python -m backupscope inventory --host YOUR_RESTIC_HOST --output inventory.local.json
python -m backupscope init --inventory inventory.local.json --output policy.local.json
```

Подставьте реальные пути вместо примеров. Наличие путей и свежесть не доказывают полноту, целостность, согласованность БД или успешное восстановление. Сохраните проверки целостности и пробные восстановления.

Если файл не найден, проверьте текущую папку. Перед отправкой отчёта удалите
чувствительные имена, пути и host. В issue укажите версию, команду, ожидаемый
и фактический результат и минимальный обезличенный пример.

[Полное руководство](../README.md) · [Сообщить об ошибке](https://github.com/HexCine/backupscope/issues)
