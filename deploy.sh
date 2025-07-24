#!/bin/bash
set -ex

echo "🚀 Starting deploy script..."

# 1. Nainstalujeme správné CLI
echo "📦 Installing Keboola Developer Portal CLI v2..."
pip install --no-cache-dir keboola.developer-portal-cli-v2 || {
  echo "❌ Failed to install keboola.developer-portal-cli-v2.";
  exit 1;
}
echo "✅ CLI installed successfully."

# 2. Získáme info o repozitáři a ECR přihlašovacích údajích
echo "🔑 Fetching repository info & ECR credentials..."
kbc-developer-portal get-repository \
  --username "$KBC_DEVELOPERPORTAL_USERNAME" \
  --password "$KBC_DEVELOPERPORTAL_PASSWORD" \
  --vendor "$KBC_DEVELOPERPORTAL_VENDOR" \
  --app "$KBC_DEVELOPERPORTAL_APP" \
  --url https://developer-portal.keboola.com \
  --file .kbc-developer-portal-cli-repository || {
    echo "❌ Failed to get repository info.";
    exit 1;
}
echo "✅ Repository info fetched."

# 3. Načteme ECR URL a heslo
ECR_REPO_URL=$(jq -r '.ecr.url' .kbc-developer-portal-cli-repository)
ECR_PASSWORD=$(jq -r '.ecr.password' .kbc-developer-portal-cli-repository)
echo "🔗 ECR_REPO_URL: $ECR_REPO_URL"

# 4. Přihlášení do Docker ECR registru
echo "🔐 Logging into Docker ECR..."
echo "$ECR_PASSWORD" | docker login -u AWS --password-stdin "$ECR_REPO_URL" || {
  echo "❌ Failed to login to ECR.";
  exit 1;
}
echo "✅ Logged into ECR."

# 5. Určíme tag pro Docker image
TAG="${TRAVIS_TAG:-latest}"
echo "🏷️  Using Docker image tag: $TAG"

# 6. Tagování a pushování Docker image
echo "📤 Tagging and pushing Docker image..."
docker tag "$APP_IMAGE" "$ECR_REPO_URL:$TAG" || {
  echo "❌ Failed to tag Docker image.";
  exit 1;
}
docker push "$ECR_REPO_URL:$TAG" || {
  echo "❌ Failed to push Docker image.";
  exit 1;
}
echo "✅ Docker image pushed to $ECR_REPO_URL:$TAG"

# 7. Aktualizace komponenty v Developer Portálu (jen pokud je build z tagu)
if [ -n "$TRAVIS_TAG" ]; then
  echo "🌐 Updating Keboola Developer Portal component version → $TRAVIS_TAG"
  kbc-developer-portal update-component-version \
    --repository-file .kbc-developer-portal-cli-repository \
    --version "$TRAVIS_TAG" || {
      echo "❌ Failed to update component version in Developer Portal.";
      exit 1;
  }
  echo "✅ Component version updated in Developer Portal."
else
  echo "ℹ️  Skipping Developer Portal update (not a tagged build)."
fi

echo "🎉 Deploy finished successfully!"
