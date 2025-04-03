#!/usr/bin/env bash

# exit on any error
set -e

# allow the user to enable verbose output with an env var
VERBOSE=${VERBOSE:-0}

# create a network in which to run the PMC crawler and reformed
DOCKER_NETWORK="pmc-crawler"

# which docker image to use to run the crawl.
# (you can either build pmc-crawler locally via build_all_images.sh, or use
# a version of the crawler from google's artifact repo. we're using the artifact
# repo version by default here since
CRAWLER_IMAGE=${CRAWLER_IMAGE:-"us-central1-docker.pkg.dev/cuhealthai-foundations/tools/pmc-crawler:latest"}

function echo_verbose {
    if [[ ${VERBOSE} -eq 1 ]]; then
        echo "$@"
    fi
}

# create the network for the pmc crawler and reformed, if it doesn't already exist
docker network create pmc-crawler 2>/dev/null || \
    echo_verbose "* Network '${DOCKER_NETWORK}' already exists, skipping creation..."

# ensure the format converter container is running
if ! ( docker ps | grep reformed >/dev/null 2>&1 ); then
    echo_verbose "* Reformed isn't running, booting it now..."
    docker run --rm -d \
        --name reformed \
        --network ${DOCKER_NETWORK} \
        -p 8088:8000 \
        ghcr.io/davidlougheed/reformed:sha-1b8f46b
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
    ENV_AUTHORS_SHEET_ID=$( cat ${ENV_FILE} | grep -e '^AUTHORS_SHEET_ID=' | cut -d'=' -f2 )
    ENV_AUTHORS_SHEET_PATH=$( cat ${ENV_FILE} | grep -e '^AUTHORS_SHEET_PATH=' | cut -d'=' -f2 )
    ENV_DEPARTMENT=$( cat ${ENV_FILE} | grep -e '^DEPARTMENT=' | cut -d'=' -f2 )
    ENV_DEPARTMENT_NAME=$( cat ${ENV_FILE} | grep -e '^DEPARTMENT_NAME=' | cut -d'=' -f2 )
fi

# load defaults for arguments in the following order:
# 1. from an env var with the same name as the argument
# 2. for authors, dept. args: from the ./app/.env file with the same name as the argument
# 3. for start, end dates, from a precomputed value
AUTHORS_SHEET_ID=${AUTHORS_SHEET_ID:-${ENV_AUTHORS_SHEET_ID:-""}}
AUTHORS_SHEET_PATH=${AUTHORS_SHEET_PATH:-${ENV_AUTHORS_SHEET_PATH:-""}}
DEPARTMENT=${DEPARTMENT:-${ENV_DEPARTMENT:-""}}
DEPARTMENT_NAME=${DEPARTMENT_NAME:-${ENV_DEPARTMENT_NAME:-""}}

# finally, accept the author sheet as an optional positional param
if [ ! -z "$1" ]; then
    AUTHORS_SHEET_PATH=$1
fi

if [ ! ${START_DATE+x} ]; then
    read -p "- Enter start date [${t_first_date}]: " INPUT_START_DATE
    START_DATE=${INPUT_START_DATE:-${t_first_date}}
elif [ -z "${START_DATE}" ]; then
    # use the default if an empty string was explicitly provided
    START_DATE=${t_first_date}
fi

if [ ! ${END_DATE+x} ]; then
    read -p "- Enter end date [${t_last_date}]: " INPUT_END_DATE
    END_DATE=${INPUT_END_DATE:-${t_last_date}}
elif [ -z "${END_DATE}" ]; then
    # use the default if an empty string was explicitly provided
    END_DATE=${t_last_date}
fi

# if AUTHORS_SHEET_PATH is specified, don't prompt for a smartsheet sheet ID
if [ ! -z "${AUTHORS_SHEET_PATH}" ]; then
    echo_verbose "* Using sheet specified in AUTHORS_SHEET_PATH (${AUTHORS_SHEET_PATH})"
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

if [ ! ${DEPARTMENT+x} ]; then
    read -p "- Enter department (a blank value disables this filter): " INPUT_DEPARTMENT
    DEPARTMENT=${INPUT_DEPARTMENT:-""}
else
    # clear DEPARTMENT, disabling it, if the user provided the sentinel 'n/a' string
    DEPARTMENT=""
fi

if [ -z "${DEPARTMENT_NAME}" ]; then
    read -p "- Enter department name, for customizing the report: " INPUT_DEPARTMENT_NAME
    DEPARTMENT_NAME=${INPUT_DEPARTMENT_NAME:-""}
fi

# verify inputs

# if both AUTHORS_SHEET_ID and AUTHORS_SHEET_PATH are set, raise an error
if ( [ -z "${AUTHORS_SHEET_PATH}" ] && [ -z "${AUTHORS_SHEET_ID}" ] ) || [ "${AUTHORS_SHEET_ID:-1}" -eq -1 ]; then
    echo "ERROR: either author sheet path or author sheet ID required, but neither were specified"
    exit 1
fi

# if we're using AUTHORS_SHEET_PATH, ensure that it's an accessible file
if [ ! -z "${AUTHORS_SHEET_PATH}" ] && [ ! -f "${AUTHORS_SHEET_PATH}" ]; then
    echo "ERROR: author sheet path ('${AUTHORS_SHEET_PATH}') is not accessible"
    exit 1
fi

# -------------------------------------------------------------------
# --- step 2. start the run with the entered params, storing artifacts in ./output
# -------------------------------------------------------------------

# where the input author spreadsheets are located
# (it should exist, but let's just make sure)
mkdir -p ./app/input_sheets

# where the notebook w/evaluated cells will be saved
mkdir -p intermediate

# where the final reports are stored
mkdir -p output

# if a local sheet was used, copy that into the container's input staging area
if [ ! -z "${AUTHORS_SHEET_PATH}" ]; then
    cp "${AUTHORS_SHEET_PATH}" ./app/input_sheets/ 2>/dev/null || \
        echo_verbose "ERROR: failed to copy author sheet to staging area, continuing..."

    # remap author's sheet path so it's relative to this staging area
    AUTHORS_SHEET_PATH=/app/input_sheets/$( basename "${AUTHORS_SHEET_PATH}" )
fi

# clean up any old containers before running
docker rm --force pmc-crawler >/dev/null 2>&1

time (
    docker run --init -it --name pmc-crawler \
        --network ${DOCKER_NETWORK} \
        -e START_DATE="${START_DATE}" \
        -e END_DATE="${END_DATE}" \
        -e "AUTHORS_SHEET_ID=${AUTHORS_SHEET_ID}" \
        -e "AUTHORS_SHEET_PATH=${AUTHORS_SHEET_PATH}" \
        -e DEPARTMENT="${DEPARTMENT}" \
        -e DEPARTMENT_NAME="${DEPARTMENT_NAME:-''}" \
        -v $PWD/app:/app \
        -v $PWD/output:/app/_build \
        -v $PWD/intermediate:/app/_output \
        --env-file ./app/.env \
        ${CRAWLER_IMAGE}
)
