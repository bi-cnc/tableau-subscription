#!/bin/bash
set -ex

echo "Starting deploy script..."

# 1. Získání informací o repozitáři a ECR přihlašovacích údajů do lokálního souboru
echo "Obtaining repository info and ECR credentials..."
kbc-developer-portal get-repository \
  --username "$KBC_DEVELOPERPORTAL_USERNAME" \
  --password "$KBC_DEVELOPERPORTAL_PASSWORD" \
  --vendor "$KBC_DEVELOPERPORTAL_VENDOR" \
  --app "$KBC_DEVELOPERPORTAL_APP" \
  --url https://developer-portal.keboola.com \
  --file .kbc-developer-portal-cli-repository || { echo "Failed to get repository info."; exit 1; }

# 2. Načtení ECR URL a hesla ze souboru
ECR_REPO_URL=$(jq -r '.ecr.url' .kbc-developer-portal-cli-repository)
ECR_PASSWORD=$(jq -r '.ecr.password' .kbc-developer-portal-cli-repository)
echo "ECR_REPO_URL: $ECR_REPO_URL"

# 3. Přihlášení do Docker ECR registru
echo "Logging into Docker ECR registry..."
echo "$ECR_PASSWORD" | docker login -u AWS --password-stdin "$ECR_REPO_URL" || { echo "Failed to login to ECR."; exit 1; }

# 4. Určení tagu pro Docker image
TAG="${TRAVIS_TAG:-latest}"
echo "Using image tag: $TAG"

# 5. Tagování a pushování Docker obrazu
echo "Tagging and pushing Docker image..."
docker tag "$APP_IMAGE" "$ECR_REPO_URL:$TAG" || { echo "Failed to tag Docker image."; exit 1; }
docker push "$ECR_REPO_URL:$TAG" || { echo "Failed to push Docker image."; exit 1; }

# 6. Aktualizace komponenty v Developer Portálu
if [ -n "$TRAVIS_TAG" ]; then
  echo "Updating component version in Developer Portal to $TRAVIS_TAG..."
  kbc-developer-portal update-component-version \
    --repository-file .kbc-developer-portal-cli-repository \
    --version "$TRAVIS_TAG" || { echo "Failed to update component version."; exit 1; }
else
  echo "Skipping component version update in Developer Portal (not a tagged build)."
fi

echo "Deploy script finished successfully."
