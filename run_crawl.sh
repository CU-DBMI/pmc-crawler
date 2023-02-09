#!/usr/bin/env bash

# which docker image to use to run the crawl.
# (you can either build pmc-crawler locally via build_all_images.sh, or use
# a version of the crawler from google's artifact repo. we're using the artifact
# repo version by default here since
CRAWLER_IMAGE=${CRAWLER_IMAGE:-"us-central1-docker.pkg.dev/cuhealthai-foundations/tools/pmc-crawler:latest"}

# ensure the format converter container is running
if ! ( docker ps | grep reformed >/dev/null 2>&1 ); then
    echo "* Reformed isn't running, booting it now..."
    docker run -d --name reformed -p 8088:8000 ghcr.io/davidlougheed/reformed:sha-1b8f46b
fi

# produce default first-of-month and last-of-month values to use as start date, end date
t_first_date=$(date +%Y/%m/01)

if [[ "$OSTYPE" =~ ^darwin ]]; then
    t_last_date=$( date -v1d -v+1m -v-1d +%Y/%m/%d )
else
    t_last_date=$( date -d "`date +%Y%m01` +1 month -1 day" +%Y/%m/%d )
fi

# ---------------------------------------
# --- step 1. prompt for run parameters
# ---------------------------------------

# pre-step: extract params from the .env file, if available
ENV_FILE="./app/.env"
if [ -f "${ENV_FILE}" ]; then
    ENV_AUTHORS_SHEET_ID=$( cat ${ENV_FILE} | grep -e '^AUTHORS_SHEET_ID' | cut -d'=' -f2 )
    ENV_AUTHORS_SHEET_PATH=$( cat ${ENV_FILE} | grep -e '^AUTHORS_SHEET_PATH' | cut -d'=' -f2 )
    ENV_DEPARTMENT=$( cat ${ENV_FILE} | grep -e '^DEPARTMENT' | cut -d'=' -f2 )
fi

# load defaults for arguments in the following order:
# 1. from an env var with the same name as the argument
# 2. for authors, dept. args: from the ./app/.env file with the same name as the argument
# 3. for start, end dates, from a precomputed value
START_DATE=${START_DATE:-${t_first_date}}
END_DATE=${END_DATE:-${t_last_date}}
AUTHORS_SHEET_ID=${AUTHORS_SHEET_ID:-${ENV_AUTHORS_SHEET_ID:-""}}
AUTHORS_SHEET_PATH=${AUTHORS_SHEET_PATH:-${ENV_AUTHORS_SHEET_PATH:-""}}
DEPARTMENT=${DEPARTMENT:-${ENV_DEPARTMENT:-""}}

# finally, accept the author sheet as an optional positional param
if [ ! -z "$1" ]; then
    AUTHORS_SHEET_PATH=$1
fi

read -p "- Enter start date [${START_DATE}]: " INPUT_START_DATE
START_DATE=${INPUT_START_DATE:-${START_DATE}}

read -p "- Enter end date [${END_DATE}]: " INPUT_END_DATE
END_DATE=${INPUT_END_DATE:-${END_DATE}}

# if AUTHORS_SHEET_PATH is specified, don't prompt for a smartsheet sheet ID
if [ ! -z "${AUTHORS_SHEET_PATH}" ]; then
    echo "* Using sheet specified in AUTHORS_SHEET_PATH (${AUTHORS_SHEET_PATH})"
else
    # default to prompting for an author sheet ID
    if [ -z "${AUTHORS_SHEET_ID}" ]; then
        # if it's unset, give them a chance to set it
        read -p "- Enter smartsheet ID for authors' sheet [${AUTHORS_SHEET_ID}]: " INPUT_AUTHORS_SHEET_ID
        AUTHORS_SHEET_ID=${INPUT_AUTHORS_SHEET_ID:-${AUTHORS_SHEET_ID}}
    else
        # it was in the env file, so let the user know
        echo "* Got AUTHORS_SHEET_ID from .env file: ${AUTHORS_SHEET_ID}"
    fi
fi

read -p "- Enter department (a blank value disables this filter): " INPUT_DEPARTMENT
DEPARTMENT=${INPUT_DEPARTMENT:-""}

# verify inputs

# if both AUTHORS_SHEET_ID and AUTHORS_SHEET_PATH are set, raise an error
if ( [ -z "${AUTHORS_SHEET_PATH}" ] && [ -z "${AUTHORS_SHEET_ID}" ] ) || [ "${AUTHORS_SHEET_ID:-1}" -eq -1 ]; then
    echo "ERROR: either author sheet path or author sheet ID required, but neither were specified"
    exit 1
fi

# ensure that AUTHORS_SHEET_PATH is a file
if [ ! -f "${AUTHORS_SHEET_PATH}" ]; then
    echo "ERROR: author sheet path ('${AUTHORS_SHEET_PATH}') is not accessible"
    exit 1
fi

# -------------------------------------------------------------------
# --- step 2. start the run with the entered params, storing artifacts in ./output
# -------------------------------------------------------------------

mkdir -p ./app/input_sheets # should exist, but let's just make sure
mkdir -p output
mkdir -p intermediate

# if a local sheet was used, copy that into the container's input staging area
if [ ! -z "${AUTHORS_SHEET_PATH}" ]; then
    cp "${AUTHORS_SHEET_PATH}" ./app/input_sheets/
    # remap author's sheet path so it's relative to this staging area
    AUTHORS_SHEET_PATH=/app/input_sheets/$( basename "${AUTHORS_SHEET_PATH}" )
fi

# clean up any old containers before running
docker rm --force pmc-crawler >/dev/null 2>&1

time (
    docker run --name pmc-crawler \
        --network host \
        -e START_DATE=${START_DATE} \
        -e END_DATE=${END_DATE} \
        -e "AUTHORS_SHEET_ID=${AUTHORS_SHEET_ID}" \
        -e "AUTHORS_SHEET_PATH=${AUTHORS_SHEET_PATH}" \
        -e DEPARTMENT=${DEPARTMENT} \
        -v $PWD/app:/app \
        -v $PWD/output:/app/_build \
        -v $PWD/intermediate:/app/_output \
        --env-file ./app/.env \
        ${CRAWLER_IMAGE}
)
