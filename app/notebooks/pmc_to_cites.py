#!/usr/bin/env python
# coding: utf-8

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

# In[1]:


import calendar
import json
import logging
import os
import copy
import subprocess
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
logging.basicConfig(level=logging.INFO)

BUILD_FOLDER = os.environ.get("BUILD_FOLDER", "/app/_build")


# In[2]:


# Papermill Parameters Cell
# These can be used as arguments via papermill

environment = "dev"

# Set any dates (as string in the format yyyy/mm/dd) for searching a month's cites
# Leave these empty to generate for the current month.
start_date: str = "2023/01/01"
end_date: str = "2023/01/31"

# Optional NCBI API key
API_KEY = "6f104848ae7ff47f67a69b6b0df250392608"

# NCBI API email
API_EMAIL = "cuhealthai-softwareengineering@cuanschutz.edu"


# In[3]:


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


# month_end_date(prepared_date)


# In[4]:


prepared_date = datetime.today().strftime("%Y/%m/%d")

# this is the old "report" ID that i can't seem to find and nobody knows anything about it
authors_sheet_id = 2181104695306116
# this is the ID from jerome's "DBMI Contact List" spreadsheet
# it appears to contain the correct info, so we're going with this
alt_authors_sheet_id = 4075591415687044

if end_date:
    # if the parameter date has been set, use it...
    month_starting_date, month_ending_date = month_end_date(end_date)
else:
    # ... otherwise use today.
    month_starting_date, month_ending_date = month_end_date(prepared_date)

BUILD_MARKDOWN_FILEROOT = f"cites_monthly-{month_ending_date.replace('/','-')}"
BUILD_MARKDOWN_FILENAME = f"{BUILD_MARKDOWN_FILEROOT}.md"
BUILD_PDF_FILENAME = f"{BUILD_MARKDOWN_FILEROOT}.pdf"
BUILD_DOCX_FILENAME = f"{BUILD_MARKDOWN_FILEROOT}.docx"

print(month_starting_date, month_ending_date)


# In[5]:


# override the month start date from parameters if any
if start_date:
    month_starting_date = start_date

month_starting_date


# In[6]:


# check the environment vars for secrets

env_file = f".env-{environment}"
log.info("Loading the .env file from %s", env_file)
dotenv.load_dotenv(dotenv.find_dotenv(env_file))

assert os.environ.get("SMARTSHEET_KEY"), f"SMARTSHEET_KEY not found in {env_file}"

if os.environ.get("API_KEY"):
    # if the ncbi key has been set in environment
    API_KEY = os.environ.get("API_KEY")


# In[7]:


# connect smartsheet client
ss_client = smartsheet.Smartsheet(os.environ.get("SMARTSHEET_KEY"))
ss_client.errors_as_exceptions(True)


# In[8]:


# if we don't have an API_KEY from parameters
# and an environment variable is set for this
# set the API_KEY to the environment var
if not API_KEY and os.environ.get("NCBI_API_KEY", ""):
    API_KEY = os.environ["NCBI_API_KEY"]

# set rate limit based on whether there's an API_KEY
# based on NCBI requirements
if API_KEY:
    NCBI_RATE_LIMIT = 10
else:
    NCBI_RATE_LIMIT = 3

NCBI_RATE_LIMIT


# In[9]:


# will write out to a folder
if not os.path.exists(BUILD_FOLDER):
    os.makedirs(BUILD_FOLDER)


# ## Fetch authors list

# In[10]:


# authors_sheet = ss_client.Reports.get_report(authors_sheet_id)
# the above fetched a report, but i have no idea what that is...
# we'll fetch the sheet instead using the "alt" ID
authors_sheet = ss_client.Sheets.get_sheet(alt_authors_sheet_id)


# In[11]:


# break down the cell IDs into a quick lookup box
cell_ids = ["Row ID"]
for column in authors_sheet.columns:
    my_column = column.to_dict()
    cell_ids.append(my_column["title"])

cell_ids


# In[12]:


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


# In[13]:


# put it together as a dataframe
authors_df = pd.DataFrame(rows_list, columns=cell_ids)
# only want primary
authors_df = authors_df.loc[authors_df["Primary Department"] == "DBMI"]
authors_df.set_index("Official Name", inplace=True)
authors_df["NCBI search term"].fillna("", inplace=True)
authors_df["ORCID number"].fillna("", inplace=True)
authors_df


# In[14]:


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


# In[15]:


# set the logic for the search terms
authors_df['full NCBI search term'] = authors_df.apply(build_search_term, axis=1)
authors_df


# In[16]:


# helpful for debugging and development only
# authors_df = authors_df.sample(frac=0.10)
# authors_df


# In[17]:


@sleep_and_retry
@limits(calls=NCBI_RATE_LIMIT, period=60)
def search_ncbi(
    term: str,
    mindate: str,
    maxdate: str,
    api_key: str = None,
    email: str = API_EMAIL,
) -> List[str]:
    """
    Look up IDs given a search term,
    a beginning year, and an optional API key.

    NCBI asks that we use an API key,
    which increases API calls to 10/minute, instead of 3/minute.

    Returns status code and a list of IDs
    """

    log.info(f"Looking up NCBI records for {term}, between {mindate} and {maxdate}.")
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
        r = requests.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi", params
        )
        if r.status_code == 200:
            result = r.json()["esearchresult"]
        else:
            logging.error(f"NCBI returned a status code of {r.status_code}.")
            logging.error("URL: ", r.url)
            logging.error("Details: ", r.json())
            break

        if len(result["idlist"]) == 0:
            # no more IDs
            break
        else:
            # append the IDs to the results...
            ids = ids + result["idlist"]
            # and move the start chunk up by the size of retmax
            params["retstart"] += params["retmax"]

    return r.status_code, ids


# In[18]:


print(API_KEY)


# In[19]:


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
            logging.warning(f"Cannot find a search term for `{author}`")
            skipped_authors.add(author)
            continue

        logging.info(f"Looking up `{author}` using {search_term}")
        status_code, ids = search_ncbi(
            term=search_term,
            mindate=month_starting_date,
            maxdate=month_ending_date,
            api_key=API_KEY,
        )
        log.debug("pubmed ids fetched from NCBI: %s", ids)

        for id in ids:
            if not id_dict.get(id):
                # create an empty nested dict
                id_dict[id] = {"authors": []}
            id_dict[id]["authors"].append(author)


# How many items found?

# In[20]:


len(id_dict)


# In[21]:


id_dict


# In[22]:


# create a list of pubmed ids and fetch the citation json...
# takes a good bit of time with a large list.
# Manubot, which uses NCBI, I presume is taking time
ids = [f"pubmed:{id}" for id in id_dict.keys()]

print("IDs: ", ids)

citations = Citations(ids)

print("Built citations, running get_csl_items...")
cites = citations.get_csl_items()
cites


# In[23]:


# sometimes, in what I can only figure are sunspots or something,
# an author dictionary in 'authors' will be empty... and this
# causes big problems down the line. So I remove the empties.
for cite in cites:
    while {} in cite["author"]:
        cite["author"].remove({})


# In[24]:


# I'm going to want to sort these later.
for rec in cites:
    key = rec["PMID"]

    id_dict[key]["csljson"] = rec
    id_dict[key]["title"] = rec["title"].strip()

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


# In[25]:


# sort the dictionary
df = pd.DataFrame.from_dict(id_dict, orient="index")
df.sort_values(by="title", inplace=True)
df


# In[26]:


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


# In[27]:


# load the citation style
# (we presume here that the folder with the notebook is the current working directory)
bib_style = CitationStylesStyle("manubot-style-title-case.csl")
bib_style


# In[28]:


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


# In[29]:


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
cite_markdown_df


# In[30]:


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


# In[31]:


# and finally a reporting DF
report_df = df.merge(cite_markdown_df, left_index=True, right_index=True)
report_df


# ## Build up the markdown

# In[32]:


log.info(f"Writing file {BUILD_MARKDOWN_FILENAME} to {BUILD_FOLDER}")
with open(
    os.path.join(BUILD_FOLDER, BUILD_MARKDOWN_FILENAME), "w", encoding="utf-8"
) as f:
    f.write(f"# Department of Biomedical Informatics (DBMI)\n\n")

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

# In[33]:


def convert(input_path, input_fmt, output_path, output_fmt):
    url = f"http://localhost:8088/api/v1/from/{input_fmt}/to/{output_fmt}"
    
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


# In[34]:


url = "http://localhost:8088/api/v1/from/markdown/to/pdf"

input_path = os.path.join(BUILD_FOLDER, BUILD_MARKDOWN_FILENAME)
output_path = os.path.join(BUILD_FOLDER, BUILD_PDF_FILENAME)

convert(
    input_path = os.path.join(BUILD_FOLDER, BUILD_MARKDOWN_FILENAME), input_fmt="markdown",
    output_path = os.path.join(BUILD_FOLDER, BUILD_PDF_FILENAME), output_fmt="pdf"
)


# In[35]:


url = "http://localhost:8088/api/v1/from/markdown/to/docx"

convert(
    input_path = os.path.join(BUILD_FOLDER, BUILD_MARKDOWN_FILENAME), input_fmt="markdown",
    output_path = os.path.join(BUILD_FOLDER, BUILD_DOCX_FILENAME), output_fmt="docx"
)


# In[ ]:




