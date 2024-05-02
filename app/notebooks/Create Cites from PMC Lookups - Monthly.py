# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:light
#     text_representation:
#       extension: .py
#       format_name: light
#       format_version: '1.5'
#       jupytext_version: 1.16.1
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# # Published Items for the Center for Health AI - Monthly
#
# This takes a list of authors and searches for any items published for the provided month, grabs the proper citation from manubot-cite, and creates a markdown and MS Word document.
#
# The smartsheet with the author search terms can be found here: https://app.smartsheet.com/sheets/rCfg3F64V9c4wH6Q9vcwQwqxF8XqhWJchpQfgRR1?view=grid
#
# - 2021/12/20 First demo (ST)
# - 2022/01/18 Fetch pubmed instead of PMC ids (ST)
# - 2022/01/19 Added caching to help dev go faster (ST)
# - 2022/06/24 Changes for monthly counts (DB)
# - 2022/06/12 Pull user list from smartsheet (ST)
# - 2022/08/09 Include ORCiD in search terms

# when cells finish running, triggers a push notification in compatible browsers
# !pip install jupyterlab_notify
# %load_ext jupyterlab_notify
# %notify_all

# +
import sys
import calendar
import json
import logging
import os
import copy
import subprocess
import time
from dateutil import parser
from datetime import date, datetime, timedelta
from typing import Dict, List, Union
import numpy as np
import manubot
import pandas as pd
import requests
import smartsheet
import scrapbook as sb
import dotenv

from prefect import task, flow
from prefect.client import get_client

from manubot.cite.citations import Citations
from manubot.cite.citekey import citekey_to_csl_item
from citeproc.source.json import CiteProcJSON
from citeproc import CitationStylesStyle, CitationStylesBibliography
from citeproc import Citation, CitationItem
from citeproc import formatter

from ratelimit import RateLimitException, limits, sleep_and_retry

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG, stream=sys.stdout, force=True)

# +
# set variables from the environment
BUILD_FOLDER_PREFIX = os.environ.get("BUILD_FOLDER_PREFIX", "/app/_build")

# (Optional) NCBI API key
NCBI_API_KEY = os.environ.get('NCBI_API_KEY')
# (Optional) NCBI API email
NCBI_API_EMAIL = os.environ.get('NCBI_API_EMAIL')

# + jupyter={"source_hidden": true} tags=["parameters"]
# Papermill Parameters Cell
# These can be used as arguments via papermill

# Set any dates (as string in the format yyyy/mm/dd) for searching a month's cites
# Leave these empty to generate for the current month.
start_date: str = "2024/02/01"
end_date: str = "2023/03/01"

# this is the ID from jerome's "DBMI Contact List" spreadsheet
# it appears to contain the correct info, so we're going with this
authors_sheet_id:int = os.environ.get('AUTHORS_SHEET_ID', -1)

# alternatively, the user may supply a path to a file
authors_sheet_path:str = os.environ.get('AUTHORS_SHEET_PATH')

# the name of the department by which to filter authors, i.e. the value on which to match against the "Primary Department" column
# if null or blank, disables filtering by department
department:str = None

# the display name of the department, used to customize the report
department_name:str = None

# +
# !!!!!

# FIXME: remove this when we're actually using it

# Customizations for Physiology & Biophysics
# authors_sheet_path = "/app/input_sheets/DBMI Contact List.xlsx" 
authors_sheet_path = "/app/input_sheets/Physiology & Biophysics Contact List.xlsx"
# authors_sheet_path = "/app/input_sheets/Dec 1st 2023 - Physiology & Biophysics Contact List.xlsx"

start_date = "2024/04/01"
end_date = "2024/04/30"
# start_date = "2023/01/01"
# end_date = "2024/01/31"

department_name = "Department of Physiology & Biophysics"

# !!!!!


# +
# first, determine if the user is supplying a local file, in which case don't do anything with smartsheet
author_sheet_valid = authors_sheet_path is not None and authors_sheet_path.strip() != ""

# check the environment vars for secrets

try:
    env_file = "/app/.env"
    log.info("Loading the .env file from %s", env_file)
    dotenv.load_dotenv(dotenv.find_dotenv(env_file))
except OSError as ex:
    print(f".env file not found, continuing... (Exception: {ex})")

if not author_sheet_valid:
    assert os.environ.get("SMARTSHEET_KEY"), f"SMARTSHEET_KEY not found in the environment"

# -

def month_end_date(a_date: str) -> (str, str):
    """
    Calculate the month start and end date, given _any_ date.

    Returns month_start_date, month_end_date.
    """
    date_format_string = "%Y/%m/%d"

    this_date = datetime.strptime(a_date, date_format_string)
    month = this_date.month
    year = this_date.year

    start_date = f"{year}/{month}/1"

    month += 1
    if month == 13:
        month = 1
        year += 1

    work_date = datetime.strptime(f"{year}/{month}/1", date_format_string)
    end_date = (work_date - timedelta(days=1)).strftime(date_format_string)

    return start_date, end_date



month_end_date(end_date)

# +
prepared_date = datetime.today().strftime("%Y/%m/%d")

if end_date:
    # if the parameter date has been set, use it...
    month_starting_date, month_ending_date = month_end_date(end_date)
else:
    # ... otherwise use today.
    month_starting_date, month_ending_date = month_end_date(prepared_date)

BUILD_MARKDOWN_FILEROOT = f"cites_monthly-{month_ending_date.replace('/','-')}"
BUILD_MARKDOWN_FILENAME = f"{BUILD_MARKDOWN_FILEROOT}.md"
BUILD_SHEET_FILENAME = f"{BUILD_MARKDOWN_FILEROOT}.xlsx"
BUILD_PDF_FILENAME = f"{BUILD_MARKDOWN_FILEROOT}.pdf"
BUILD_DOCX_FILENAME = f"{BUILD_MARKDOWN_FILEROOT}.docx"

print(month_starting_date, month_ending_date)

# +
# override the month start date from parameters if any
if start_date:
    month_starting_date = start_date
    
# override the ending date, too (why did it ever work differently?)
if end_date:
    month_ending_date = end_date

month_starting_date

# +
# set rate limit based on whether there's an API_KEY
# based on NCBI requirements
if NCBI_API_KEY:
    NCBI_RATE_LIMIT = 10
else:
    NCBI_RATE_LIMIT = 3

NCBI_RATE_LIMIT

# the duration, in seconds, during which we can issue NCBI_RATE_LIMIT calls
NCBI_CALL_PERIOD = 3 # from NCBI's docs

# +
# ensure the output folder exists, and group the results of this run into a folder created from the start and end date
BUILD_FOLDER = os.path.join(BUILD_FOLDER_PREFIX, f"{month_starting_date}_to_{month_ending_date}".replace("/", "-"))

# will write out to a folder
if not os.path.exists(BUILD_FOLDER):
    os.makedirs(BUILD_FOLDER)
# -

# ## Fetch authors list
#
# Uses whichever one of `authors_sheet_id` or `authors_sheet_path` is specified to fetch the list of authors. If it's the `_id` version, the sheet is fetched from Smartsheet by its ID, whereas if it's `_path` it's loaded from a local Excel/CSV file. If both are specified, an error is returned.

# +
if author_sheet_valid:
    print(f"Loading authors from local spreadsheet file: {authors_sheet_path}")
    
    from pathlib import Path
    # load up the local file instead
    pth = Path(authors_sheet_path)
    authors_df = pd.read_excel(pth)
    
elif authors_sheet_id is not None and str(authors_sheet_id).strip() != '' and int(authors_sheet_id) != -1:
    print(f"Loading authors from Smartsheet by ID: {authors_sheet_id}")
    
    # connect smartsheet client
    ss_client = smartsheet.Smartsheet(os.environ.get("SMARTSHEET_KEY"))
    ss_client.errors_as_exceptions(True)

    # authors_sheet = ss_client.Reports.get_report(authors_sheet_id)
    # the above fetched a report, but i have no idea what that is...
    # we'll fetch the sheet instead using the "alt" ID
    authors_sheet = ss_client.Sheets.get_sheet(authors_sheet_id)

    # break down the cell IDs into a quick lookup box
    cell_ids = ["Row ID"]
    for column in authors_sheet.columns:
        my_column = column.to_dict()
        cell_ids.append(my_column["title"] or "NO_TITLE")

    # cell_ids

    # break down the cells into a list of lists for a later dataframe
    rows_list = []
    for row in authors_sheet.rows:
        row_list = [row.id]
        for cell in row.cells:
            if cell.display_value:
                row_list.append(cell.display_value)
            else:
                # just in case there's a None in here, use NaN instead
                if cell.value:
                    row_list.append(cell.value)
                else:
                    row_list.append(np.NaN)

        rows_list.append(row_list)
    
    # put it together as a dataframe
    authors_df = pd.DataFrame(rows_list, columns=cell_ids)

else:
    raise Exception("One of authors_sheet_path or authors_sheet_id must be specified, but neither were provided.")

# +
# only want primary
if department and department.strip() != "":
    authors_df = authors_df.loc[authors_df["Primary Department"] == department]

authors_df.set_index("Official Name", inplace=True)
authors_df["NCBI search term"].fillna("", inplace=True)
authors_df["ORCID number"].fillna("", inplace=True)
# authors_df
# -

def build_search_term(row):
    """
    Function to build up the search term. Used by a dataframe apply()
    
    https://pubmed.ncbi.nlm.nih.gov/help/
    """
    
    search_terms = []
    
    if row['ORCID number']:
        orcid_term = f"(orcid {row['ORCID number']} [auid])"
        #orcid_term = f"({row['ORCID number']}[Author - Identifier])"
        search_terms.append(orcid_term)
        
    if row["NCBI search term"]:
        search_terms.append(row["NCBI search term"])

    if len(search_terms) > 0:
        # group the search terms with an OR, then and that group with CU
        return f'(({" OR ".join(search_terms)}) AND ("University of Colorado"))'
    else:
        return ""


# set the logic for the search terms
authors_df['full NCBI search term'] = authors_df.apply(build_search_term, axis=1)

# +
# cache requests to NCBI so these can be accelerated on subsequent runs
import requests_cache

session = requests_cache.CachedSession('ncbi_authors_cache')

# if we hit an error, start with the default wait and double it every time we hit an error again for this URL
backoff = NCBI_CALL_PERIOD

# FIMXE: because we run multiple requests in a loop within this function, these limits are only
#  respected for each unique query. the code that runs a single request should be pulled out
#  into its own function with these decorators applied to it.
@sleep_and_retry
@limits(calls=NCBI_RATE_LIMIT, period=NCBI_CALL_PERIOD)
def search_ncbi(
    term: str,
    mindate: str,
    maxdate: str,
    api_key: str = None,
    email: str = NCBI_API_EMAIL,
) -> List[str]:
    """
    Look up IDs given a search term,
    a beginning year, and an optional API key.

    NCBI asks that we use an API key,
    which increases API calls to 10/minute, instead of 3/minute.

    Returns status code and a list of IDs
    """

    # the delay before we reissue a request; reset to NCBI_CALL_PERIOD if we succeed
    # doubled every time we make an error
    global backoff

    # log.info(f"Looking up NCBI records for {term}, between {mindate} and {maxdate}.")
    ids = []

    params = {
        "term": term,
        "format": "pmid",
        "tool": "CUAnschutz-Center_for_Health_AI-DEV",
        "email": email,
        "format": "json",
        "retmax": 100,
        "retstart": 0,
        # note: date format is in yyyy/mm/dd
        "mindate": mindate,
        "maxdate": maxdate,
    }

    if api_key:
        params["api_key"] = api_key

    # page through the results until there are no more ids
    while True:
        r = session.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi", params=params
        )

        if r.status_code == 200:
            result = r.json()["esearchresult"]
            # reset the backoff if it went ok
            backoff = NCBI_CALL_PERIOD
        else:
            # exponentially back off
            backoff *= 2 # double the backoff

            try:
                data = r.json()
            except:
                data = None

            log.error(f"NCBI returned a status code of {r.status_code} for URL: {r.url}; retrying in {backoff} seconds... (Details: {data or 'n/a'})")

            time.sleep(backoff) # sleep for a while
            break # and try again

        if len(result["idlist"]) == 0:
            # no more IDs
            break
        else:
            # append the IDs to the results...
            ids = ids + result["idlist"]
            # and move the start chunk up by the size of retmax
            params["retstart"] += params["retmax"]

    return r.status_code, ids


# +
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

# I would like to do this in parallel, but the deal with NCBI is we agree not to do that
id_dict = {}

log.info(
    f"Looking up pubmed IDs from NCBI between {month_starting_date} and {month_ending_date}"
)

skipped_authors = set()

with logging_redirect_tqdm():
    for author, row in tqdm(authors_df.iterrows(), total=authors_df.shape[0]):
        if row['full NCBI search term']:
            search_term = row['full NCBI search term']
        else:
            log.warning(f"Cannot find a search term for `{author}`")
            skipped_authors.add(author)
            continue

        log.info(f"Looking up `{author}` using {search_term}")
        status_code, ids = search_ncbi(
            term=search_term,
            mindate=month_starting_date,
            maxdate=month_ending_date,
            api_key=NCBI_API_KEY,
        )
        log.debug("pubmed ids fetched from NCBI: %s", ids)

        for id in ids:
            if not id_dict.get(id):
                # create an empty nested dict
                id_dict[id] = {"authors": []}
            id_dict[id]["authors"].append(author)
# -

ids

# +
# create a list of pubmed ids and fetch the citation json...
# takes a good bit of time with a large list.
# Manubot, which uses NCBI, I presume is taking time
ids = [f"pubmed:{id}" for id in id_dict.keys()]

# print("IDs: ", ids)

citations = Citations(ids, prune_csl_items=False)

print("Built citations, running get_csl_items...")
cites = citations.get_csl_items()
# cites
# -

# sometimes, in what I can only figure are sunspots or something,
# an author dictionary in 'authors' will be empty... and this
# causes big problems down the line. So I remove the empties.
for cite in cites:
    while {} in cite["author"]:
        cite["author"].remove({})

citations

cites

# I'm going to want to sort these later.
for rec in cites:
    key = rec["PMID"]

    id_dict[key]["csljson"] = rec
    id_dict[key]["title"] = rec.get("title", "NO_TITLE").strip()

    # all this for the date!
    if rec.get("issued"):
        issued_date_parts = rec["issued"]["date-parts"][0]
        date_str = str(issued_date_parts[0])
        try:
            date_str += f"/{issued_date_parts[1]}"
            try:
                date_str += f"/{issued_date_parts[2]}"
            except:
                pass
        except:
            pass

        id_dict[key]["issued_date"] = date_str

id_dict

# +
# sort the dictionary
df = pd.DataFrame.from_dict(id_dict, orient="index")

df.sort_values(by="title", inplace=True)

# df

# +
# get the counts by author
author_counts_df = (
    df.explode("authors")
    .groupby("authors")["title"]
    .count()
    .to_frame()
    .rename(columns={"title": "title count"})
)

# merge the counts into our main author df
author_info_df = authors_df.merge(author_counts_df, how="inner", left_index=True, right_index=True)
# -

# load the citation style
# (we presume here that the folder with the notebook is the current working directory)
bib_style = CitationStylesStyle("manubot-style-title-case.csl")
# bib_style

def create_bibliography(cites: List):
    """
    Create the citeproc-py bibliography, passing it the:
      * CitationStylesStyle,
      * BibliographySource (CiteProcJSON in this case), and
      * a formatter (plain, html, or you can write a custom formatter)

    Created as function to hand in cites one at a time
    """
    # process the citations into a bib source
    bib_source = CiteProcJSON(cites)

    bibliography = CitationStylesBibliography(bib_style, bib_source, formatter.html)

    # register the citations in the bibliography
    for key, entry in bib_source.items():
        citation = Citation([CitationItem(key)])
        bibliography.register(citation)

    return bibliography.bibliography()


# +
# run through the cites one at a time
cite_markdown = []
for cite in cites:
    new_dict = {"PMID": cite["PMID"]}

    # I'm only handing them in one at a time
    result = create_bibliography([cite])
    new_dict["markdown"] = str(result[0])

    cite_markdown.append(new_dict)

# create a df for merging
cite_markdown_df = pd.DataFrame(cite_markdown).set_index("PMID")
# cite_markdown_df

# +
# manubot gives out HTML, and <i> is interpreted correctly,
# but maybe because <b> isn't <strong> or something,
# the HTML doesn't quite all work. Thus replacing...
# somewhat roughly


def markdown_me(row):
    temp_line = row["markdown"]
    temp_line = temp_line.replace("<b>", " **").replace("</b>", "** ")
    temp_line = temp_line.replace("<i>", "_").replace("</i>", "_")
    row["markdown"] = temp_line
    return row


cite_markdown_df = cite_markdown_df.apply(markdown_me, axis=1)
# -

# and finally a reporting DF
report_df = df.merge(cite_markdown_df, left_index=True, right_index=True)
# report_df

# ## Write out Summary Spreadsheet

# write out the report dataframe to a spreadsheet
out_sheet = os.path.join(BUILD_FOLDER, BUILD_SHEET_FILENAME)
with open(out_sheet, "wb") as f:
    publication_df = df[["authors", "title", "issued_date"]]
    publication_df.to_excel(f)
    log.info(f"Wrote out {out_sheet}\n")

# ## Build up the markdown

log.info(f"Writing file {BUILD_MARKDOWN_FILENAME} to {BUILD_FOLDER}")
with open(
    os.path.join(BUILD_FOLDER, BUILD_MARKDOWN_FILENAME), "w", encoding="utf-8"
) as f:
    if department_name is not None and str(department_name).strip() != "":
        f.write(f"# {department_name}\n\n")

    f.write(f"## Published Items Bibliography\n\n")
    f.write(f"For the period {month_starting_date} to {month_ending_date}\n\n")

    # In the custom CSL, I don't include the citation number.
    # This is just a numbered list now.
    for index, row in report_df.iterrows():
        f.write(f"{row['markdown']}\n\n")
        for author in row["authors"]:
            f.write(f" &mdash; <cite>{author}</cite>\n\n")
        f.write("***\n")

    f.write(f"## Authors and Search Terms\n\n")
    f.write(f"Please contact the DBMI A&O staff for changes to name, ORCID, or search terms.\n\n")

    f.write(f"|Author|NCBI Search Term|ORCiD|Title Count\n")
    f.write(f"|---|---|---|---\n")
    for index, row in author_info_df.iterrows():
        f.write(
            f"|{index}|{row['NCBI search term']}|{row['ORCID number']}|{row['title count']}\n"
        )

    if skipped_authors:
        f.write(f"## Skipped Searches\n\n")
        f.write(f"The following authors have been skipped due to a missing NCBI search term and missing ORCID.\n\n")

        for author in skipped_authors:
            f.write(
                f"- {author}\n"
            )
        
    f.write("\n")
    f.write(f"Generated {prepared_date}\n")

# ## Convert markdown to pdf and docx
#
# **experimental!**
#
# A very trick little docker container for wrapping pandoc. Very helpful. https://github.com/davidlougheed/reformed
#
# To run a local version:
#
#     docker run -d --name reformed -p 8088:8000 ghcr.io/davidlougheed/reformed:sha-1b8f46b

REFORMED_API_URL = "http://reformed:8000" # changed 'reformed' to localhost if you're accessing it from the host


def convert(input_path, input_fmt, output_path, output_fmt):
    url = f"{REFORMED_API_URL}/api/v1/from/{input_fmt}/to/{output_fmt}"
    
    try:
        with open(input_path, "rb") as f:
            r = requests.post(url, files={"document": f.read()})

        if r.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(r.content)
        else:
            raise Exception(f"Non-200 response, code {r.status_code}")

        print(f"Read in {input_path}, outputted to {output_path}")
    except Exception as ex:
        print(ex)


# +
url = f"{REFORMED_API_URL}/api/v1/from/markdown/to/pdf"

input_path = os.path.join(BUILD_FOLDER, BUILD_MARKDOWN_FILENAME)
output_path = os.path.join(BUILD_FOLDER, BUILD_PDF_FILENAME)

convert(
    input_path = os.path.join(BUILD_FOLDER, BUILD_MARKDOWN_FILENAME), input_fmt="markdown",
    output_path = os.path.join(BUILD_FOLDER, BUILD_PDF_FILENAME), output_fmt="pdf"
)

# +
url = f"{REFORMED_API_URL}/api/v1/from/markdown/to/docx"

convert(
    input_path = os.path.join(BUILD_FOLDER, BUILD_MARKDOWN_FILENAME), input_fmt="markdown",
    output_path = os.path.join(BUILD_FOLDER, BUILD_DOCX_FILENAME), output_fmt="docx"
)
