#!/usr/bin/env bash
set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

branch=${1:-main}

echo "Получаем изменения origin..."
git fetch origin

echo "Переключаемся на ветку $branch..."
git checkout "$branch"

echo "Объединяем изменения origin/$branch..."
git merge --ff-only "origin/$branch"

echo "Отправляем ветку $branch в userfork..."
git push userfork "$branch"

echo "Обновление завершено: userfork/$branch синхронизирован с origin/$branch."
