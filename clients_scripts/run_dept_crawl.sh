#!/usr/bin/env bash

# helper to make slugs out of titles
slugify () {
    echo "$1" | iconv -c -t ascii//TRANSLIT | sed -E 's/[~^]+//g' | sed -E 's/[^a-zA-Z0-9]+/-/g' | sed -E 's/^-+|-+$//g' | tr A-Z a-z
}

export INPUT_SPREADSHEET="${1?path to the input spreadsheet missing}"
export DEPARTMENT_NAME="$2"

# get the folder in which this script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
# cd to one above it, i.e. the repo root
cd $( realpath ${DIR}/.. )

# get the start and end date of the previous month for OS X and Linux
if [[ "$OSTYPE" =~ ^darwin ]]; then
    t_first_date=$( date -v1d -v-1m +%Y/%m/01 )
    t_last_date=$(date -v-$(date +%d)d "+%Y/%m/%d")
else
    t_first_date=$( date -d "`date +%Y%m01` -1 month" +%Y/%m/01 )
    t_last_date=$(date -d "-$(date +%d) days" "+%Y/%m/%d")
fi

# export vars that affect run_crawl.sh
export INPUT_DEPARTMENT_NAME=${DEPARTMENT_NAME}
export START_DATE=${START_DATE:-${t_first_date}}
export END_DATE=${END_DATE:-${t_last_date}}

# put the results in a dept-specific subfolder
SLUGIFIED_DEPT=$( slugify "${DEPARTMENT_NAME}" )
mkdir -p "./output/${SLUGIFIED_DEPT}/"
export BUILD_FOLDER_PREFIX="/app/_build/${SLUGIFIED_DEPT}"

echo "* Running crawl for:"
echo "- Department: ${DEPARTMENT_NAME}"
echo "- First date: ${START_DATE}"
echo "- Last date: ${END_DATE}"

./run_crawl.sh "${INPUT_SPREADSHEET}"
