#!/bin/bash
set -e

# 1. Stáhneme Keboola Developer Portal CLI
docker pull quay.io/keboola/developer-portal-cli-v2:latest

# 2. Získáme URL pro Keboola ECR repozitář
export REPOSITORY=$(docker run --rm \
    -e KBC_DEVELOPERPORTAL_USERNAME \
    -e KBC_DEVELOPERPORTAL_PASSWORD \
    quay.io/keboola/developer-portal-cli-v2:latest \
    ecr:get-repository ${KBC_DEVELOPERPORTAL_VENDOR} ${KBC_DEVELOPERPORTAL_APP})

# 3. Přihlásíme se do Keboola ECR
eval $(docker run --rm \
    -e KBC_DEVELOPERPORTAL_USERNAME \
    -e KBC_DEVELOPERPORTAL_PASSWORD \
    quay.io/keboola/developer-portal-cli-v2:latest \
    ecr:get-login ${KBC_DEVELOPERPORTAL_VENDOR} ${KBC_DEVELOPERPORTAL_APP})

# 4. Přetagujeme lokální image na Keboola ECR
docker tag ${APP_IMAGE}:latest ${REPOSITORY}:${TRAVIS_TAG}
docker tag ${APP_IMAGE}:latest ${REPOSITORY}:latest

# 5. Pushneme image do Keboola ECR
docker push ${REPOSITORY}:${TRAVIS_TAG}
docker push ${REPOSITORY}:latest

# 6. Pokud je tag validní verze (x.y.z), aktualizujeme Developer Portal
if echo ${TRAVIS_TAG} | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'; then
    echo "Valid version tag detected -> Updating Developer Portal"
    docker run --rm \
        -e KBC_DEVELOPERPORTAL_USERNAME \
        -e KBC_DEVELOPERPORTAL_PASSWORD \
        quay.io/keboola/developer-portal-cli-v2:latest \
        update-app-repository ${KBC_DEVELOPERPORTAL_VENDOR} ${KBC_DEVELOPERPORTAL_APP} ${TRAVIS_TAG} ecr ${REPOSITORY}
else
    echo "Skipping Developer Portal update, tag '${TRAVIS_TAG}' is not a valid version (x.y.z)"
fi
