#!/bin/bash
set -ex  # zapne debug výpisy a ukončí na první chybu

echo "=== DEBUG: Starting deploy.sh ==="
echo "TRAVIS_TAG=${TRAVIS_TAG}"
echo "APP_IMAGE=${APP_IMAGE}"
echo "KBC_DEVELOPERPORTAL_VENDOR=${KBC_DEVELOPERPORTAL_VENDOR}"
echo "KBC_DEVELOPERPORTAL_APP=${KBC_DEVELOPERPORTAL_APP}"

# Stáhneme Keboola Developer Portal CLI
docker pull quay.io/keboola/developer-portal-cli-v2:latest

echo "=== DEBUG: Getting repository URL from Keboola Developer Portal ==="
export REPOSITORY=$(docker run --rm \
    -e KBC_DEVELOPERPORTAL_USERNAME \
    -e KBC_DEVELOPERPORTAL_PASSWORD \
    quay.io/keboola/developer-portal-cli-v2:latest \
    ecr:get-repository ${KBC_DEVELOPERPORTAL_VENDOR} ${KBC_DEVELOPERPORTAL_APP})

echo "=== DEBUG: Repository URL is ${REPOSITORY} ==="

echo "=== DEBUG: Logging into ECR ==="
eval $(docker run --rm \
    -e KBC_DEVELOPERPORTAL_USERNAME \
    -e KBC_DEVELOPERPORTAL_PASSWORD \
    quay.io/keboola/developer-portal-cli-v2:latest \
    ecr:get-login ${KBC_DEVELOPERPORTAL_VENDOR} ${KBC_DEVELOPERPORTAL_APP})

echo "=== DEBUG: Tagging image ==="
docker tag ${APP_IMAGE}:latest ${REPOSITORY}:${TRAVIS_TAG}
docker tag ${APP_IMAGE}:latest ${REPOSITORY}:latest

echo "=== DEBUG: Pushing image to ECR ==="
docker push ${REPOSITORY}:${TRAVIS_TAG}
docker push ${REPOSITORY}:latest

# Pokud je tag validní verze (x.y.z), aktualizujeme Developer Portal
if echo ${TRAVIS_TAG} | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'; then
    echo "=== DEBUG: Valid version tag detected -> Updating Developer Portal ==="
    docker run --rm \
        -e KBC_DEVELOPERPORTAL_USERNAME \
        -e KBC_DEVELOPERPORTAL_PASSWORD \
        quay.io/keboola/developer-portal-cli-v2:latest \
        update-app-repository ${KBC_DEVELOPERPORTAL_VENDOR} ${KBC_DEVELOPERPORTAL_APP} ${TRAVIS_TAG} ecr ${REPOSITORY}
else
    echo "=== DEBUG: Skipping Developer Portal update, invalid tag '${TRAVIS_TAG}' ==="
fi

echo "=== DEBUG: Finished deploy.sh ==="
