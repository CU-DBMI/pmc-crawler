#!/usr/bin/env bash

IMAGE="pmc-crawler:latest"
GCP_IMAGE=${GCP_IMAGE:-"us-central1-docker.pkg.dev/cuhealthai-foundations/tools/${IMAGE}"}

# builds the image locally as $IMAGE
# also attempts to push it to our remote artifact registry, or wherever $GCP_IMAGE points
docker buildx create --name pmc-context --use 
docker buildx build --platform=linux/amd64,linux/arm64 -t ${IMAGE} ./app && (
    [ ! -z "${GCP_IMAGE}" ] \
        && ( docker tag ${IMAGE} ${GCP_IMAGE} && docker push ${GCP_IMAGE} ) \
        || echo "GCP_IMAGE unspecified, leaving image as local ${IMAGE}"
)
# clean up the build context when we're done
docker buildx rm pmc-context