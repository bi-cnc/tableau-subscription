#!/bin/bash
set -e

echo "🚀 Starting deploy script..."

# Použijeme Docker image pro CLI
echo "🔧 Obtaining repository URI..."
REPOSITORY=$(docker run --rm \
  -e KBC_DEVELOPERPORTAL_USERNAME \
  -e KBC_DEVELOPERPORTAL_PASSWORD \
  quay.io/keboola/developer-portal-cli-v2:latest \
  ecr:get-repository "$KBC_DEVELOPERPORTAL_VENDOR" "$KBC_DEVELOPERPORTAL_APP")

echo "🔐 Logging into AWS ECR..."
eval $(docker run --rm \
  -e KBC_DEVELOPERPORTAL_USERNAME \
  -e KBC_DEVELOPERPORTAL_PASSWORD \
  quay.io/keboola/developer-portal-cli-v2:latest \
  ecr:get-login "$KBC_DEVELOPERPORTAL_VENDOR" "$KBC_DEVELOPERPORTAL_APP")

echo "📦 Tagging and pushing images..."
docker tag "$APP_IMAGE":latest "$REPOSITORY":"$TRAVIS_TAG"
docker tag "$APP_IMAGE":latest "$REPOSITORY":latest
docker push "$REPOSITORY":"$TRAVIS_TAG"
docker push "$REPOSITORY":latest

echo "📡 Updating Developer Portal (if semver tag)..."
if echo "$TRAVIS_TAG" | grep -qE '^v?[0-9]+\.[0-9]+\.[0-9]+$'; then
  docker run --rm \
    -e KBC_DEVELOPERPORTAL_USERNAME \
    -e KBC_DEVELOPERPORTAL_PASSWORD \
    quay.io/keboola/developer-portal-cli-v2:latest \
    update-app-repository "$KBC_DEVELOPERPORTAL_VENDOR" "$KBC_DEVELOPERPORTAL_APP" "$TRAVIS_TAG" ecr "$REPOSITORY"
else
  echo "⚠️ Tag '$TRAVIS_TAG' není platná verze (x.y.z). Přeskakuji update Portal."
fi
