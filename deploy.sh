#!/bin/bash
set -ex

echo "🚀 Starting deploy script..."

echo "📦 Upgrading pip..."
python3 -m pip install --upgrade pip setuptools wheel

echo "📦 Installing Keboola Developer Portal CLI v2..."
pip install --no-cache-dir git+https://github.com/keboola/developer-portal-cli-v2.git@latest

echo "🔑 Logging in to Keboola Developer Portal..."
keboola-developer-portal-cli-v2 login --username "$KBC_DEVELOPERPORTAL_USERNAME" --password "$KBC_DEVELOPERPORTAL_PASSWORD"

echo "📤 Pushing the app to Keboola Developer Portal..."
keboola-developer-portal-cli-v2 update-app \
    --vendor "$KBC_DEVELOPERPORTAL_VENDOR" \
    --app "$KBC_DEVELOPERPORTAL_APP" \
    --type docker \
    --version "$TRAVIS_TAG" \
    --image "$APP_IMAGE" \
    --format json

echo "✅ Deploy finished successfully!"
