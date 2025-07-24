#!/bin/bash
set -e
set -x  # <-- přidat pro debug výpisy

echo "=== START DEPLOY ==="
echo "Tag: ${TRAVIS_TAG}"

docker pull quay.io/keboola/developer-portal-cli-v2:latest

echo "=== GETTING ECR REPO ==="
export REPOSITORY=$(docker run --rm \
  -e KBC_DEVELOPERPORTAL_USERNAME \
  -e KBC_DEVELOPERPORTAL_PASSWORD \
  quay.io/keboola/developer-portal-cli-v2:latest \
  ecr:get-repository ${KBC_DEVELOPERPORTAL_VENDOR} ${KBC_DEVELOPERPORTAL_APP})

echo "Repository URL: ${REPOSITORY}"

echo "=== LOGIN TO ECR ==="
eval $(docker run --rm \
  -e KBC_DEVELOPERPORTAL_USERNAME \
  -e KBC_DEVELOPERPORTAL_PASSWORD \
  quay.io/keboola/developer-portal-cli-v2:latest \
  ecr:get-login ${KBC_DEVELOPERPORTAL_VENDOR} ${KBC_DEVELOPERPORTAL_APP})

echo "=== DOCKER TAG + PUSH ==="
docker tag ${APP_IMAGE}:latest ${REPOSITORY}:${TRAVIS_TAG}
docker tag ${APP_IMAGE}:latest ${REPOSITORY}:latest

docker push ${REPOSITORY}:${TRAVIS_TAG}
docker push ${REPOSITORY}:latest

echo "=== UPDATE DEV PORTAL IF TAG VALID ==="
if echo ${TRAVIS_TAG} | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'; then
  docker run --rm \
    -e KBC_DEVELOPERPORTAL_USERNAME \
    -e KBC_DEVELOPERPORTAL_PASSWORD \
    quay.io/keboola/developer-portal-cli-v2:latest \
    update-app-repository ${KBC_DEVELOPERPORTAL_VENDOR} ${KBC_DEVELOPERPORTAL_APP} ${TRAVIS_TAG} ecr ${REPOSITORY}
else
  echo "Skipping Developer Portal update, tag '${TRAVIS_TAG}' is not valid"
fi
