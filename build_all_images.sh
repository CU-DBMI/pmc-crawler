#!/usr/bin/env bash

IMAGE="pmc-crawler:latest"
GCP_IMAGE=${GCP_IMAGE:-"us-central1-docker.pkg.dev/cuhealthai-foundations/tools/${IMAGE}"}

MULTI_PLATFORM_BUILD='0'
DO_IMAGE_PUSH='0'

# builds the image locally as $IMAGE
# also attempts to push it to our remote artifact registry, or wherever $GCP_IMAGE points
(
    if [ "${MULTI_PLATFORM_BUILD}" = "1" ]; then
        docker buildx create --name pmc-context --use 
        docker buildx build --platform=linux/amd64,linux/arm64 -t ${IMAGE} ./app
        # clean up the build context when we're done
        # docker buildx rm pmc-context
    else
        docker build -t ${IMAGE} ./app
    fi
) && (
    ( [ ! -z "${GCP_IMAGE}" ] && [ "${DO_IMAGE_PUSH}" = "1" ] ) \
        && ( docker tag ${IMAGE} ${GCP_IMAGE} && docker push ${GCP_IMAGE} ) \
        || echo "GCP_IMAGE or DO_IMAGE_PUSH disabled unspecified, leaving image as local ${IMAGE}"
)
