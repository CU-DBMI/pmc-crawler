# PMC Citation Crawler

For a given start and end date, this script crawls NCBI's Pubmed Central (aka
"PMC") for citations by the authors given in the input spreadsheet. It produces
a PDF report of publications for the given authors within the start and end
dates, and a CSV spreadsheet of the same information.

*Note that this is a fork of
[CU-DBMI/smartsheet-notebooks](https://github.com/CU-DBMI/smartsheet-notebooks),
but with significant changes. This repo is pruned down to just the PMC citation
crawler from that repo and adds a few quality-of-life and documentation
additions to make it easier for other people to use the crawler. Credit goes to
Steve Taylor (@staylorx) for the implementation; I (@falquaddoomi) made a few
tweaks and containerized it.*

## Requirements

You should ideally use this script from a Linux or Mac OS X machine (i.e., a GNU
environment in which you can run bash). Feel free to [file an
issue](https://github.com/CU-DBMI/pmc-crawler/issues) or reach out to me
directly if you need support for another platform, e.g. Windows.

You'll need Docker installed, which you can obtain for your platform here:
https://www.docker.com/products/docker-desktop/. If you wish to import your
 authors list from [Smartsheet](https://www.smartsheet.com/), you'll also need a
paid account, as the crawler makes use of the Smartsheet API to pull a
spreadsheet with information about the authors. You can alternatively provide
your authors list as a file (currently only as an Excel `.xlsx`), in which case
you can skip any sections that reference Smartsheet below.

## Setup

There are a few parts to setting up the crawl:
1. specifying the list of authors in a Smartsheet
2. (if using Smartsheet) giving the script access to Smartsheet via a Smartsheet
   API key
3. (optional, but encouraged) providing an NCBI API key to make queries against
   PMC

### Creating the Authors List

If you wish to use Smartsheet, you should create a new spreadsheet via their web
app. If you're using a local spreadsheet file, you should instead create a new
file (preferably in the same folder as this README) in Excel.

You'll need to first create a spreadsheet where you list the authors whose
publications you want to gather from PMC. The spreadsheet must contain at least
the following columns with the exact names, including case, below:

- "Official Name"
- "ORCID number"
- "NCBI search term"
- "Primary Department" *(only required if you want to filter authors by
  department)*

You can add any additional columns you like, which will be ignored by the
crawler.

For each row, "Official Name" is required, "Primary Department" is required if
filtering by department, and at least one of "ORCID number" or "NCBI search
term" need to be specified.

The "NCBI search term" is used to query PMC; it should look at least like
"(<Surname> <Given Name>)", but more commonly is written as "(<Surname> <Given
Name> [Author])" to constrain the returned entries to just those where the
person is tagged as an author. The search term can include any of the operators
or tags mentioned in the [PubMed Filters help
page](https://pubmed.ncbi.nlm.nih.gov/help/#help-filters). You can also use the
[NCBI Advanced Search](https://pubmed.ncbi.nlm.nih.gov/advanced/) to create
queries and copy the resulting search to your spreadsheet.

### Providing API Keys

The keys are strings of text that will be stored in the file `app/.env`; to
create that file, copy `app/.env.TEMPLATE` as `app/.env`, then open the file for
editing. You should see placeholders called `SMARTSHEET_KEY=` and
`NCBI_API_KEY=`, which we'll be filling out with values shortly.

To obtain and enter your Smartsheet API key (if using Smartsheet):
1. Open a browser to https://app.smartsheet.com/b/home
2. Click the "person" icon in the bottom left, revealing a menu
3. Select "Personal Settings..." from the menu
4. In the resulting modal dialog, select "API Access" from the left
5. Click "Generate new access token", which will prompt you for a name for the
   new key; feel free to enter anything you like.
6. Upon pressing "Ok", you will be shown a new dialog with a long key (for
example, "EiPhohXae0Iegae9DiewushenieGh4ohTeedo"). Copy the key that you just
generated and put it somewhere secret, e.g. in a notes app or local file.
7. Enter the key into the `SMARTSHEET_KEY` line in the `app/.env` file we
created earlier. For example, with the above key, the line would look like
`SMARTSHEET_KEY=EiPhohXae0Iegae9DiewushenieGh4ohTeedo`.

Optionally, you may obtain and enter an NCBI API key, which makes searching PMC
a bit faster:
1. Browse to https://www.ncbi.nlm.nih.gov/myncbi/, logging in and/or creating an
account if you don't already have on.
2. Once logged in, click your name in the top right of the window and select
"Account Settings", or simply browse to
https://www.ncbi.nlm.nih.gov/account/settings/.
3. On the Account Settings page, scroll to the section titled "API Key
   Management".
  - If you don't have a key yet, press the "Create an API Key" button.
4. Copy the long text string (e.g., "ad3da0297af65a2e4dd1bb917447bbd3c388")
5. Enter the key into the `NCBI_API_KEY` line in the `app/.env` file we created
earlier. For example, with the above key, the line would look like
`NCBI_API_KEY=ad3da0297af65a2e4dd1bb917447bbd3c388`.
6. Enter your NCBI account's email address into the line starting with
`NCBI_API_EMAIL=`, e.g. `NCBI_API_EMAIL=someone@somewhere.edu`

## Usage

### If You're Using Smartsheet

Before you begin, you'll need the ID of the authors sheet you created earlier.
You can obtain the Smartsheet sheet ID like so:
1. Open the Smartsheet author sheet you created earlier.
2. Select "File"" from the in-app menu, then "Properties..." from within that
   menu.
3. Copy the value for the field labeled "Sheet ID"; it'll be all numbers and
   approximately 16 or more characters long,

If you want to avoid having to enter the sheet ID every time you run the
crawler, you can optionally add the Sheet ID to your `app/.env` file by filling
in the value for `AUTHORS_SHEET_ID`; you will see it appear as the default value
when you run the cralwer.

### If You're Using a Local Spreadsheet

Make a note of the name of your file, as you'll be supplying it to the script
shortly.

### Running the Crawler

Once you have the requirements installed, you can run the script
`./run_crawl.sh` if you're intending to import your authors list from
Smartsheet. If you're instead using a local file, run the script with the
filename after the script, e.g. if your file were named `my_authors.xlsx` you'd
invoke it like `./run_crawl.sh my_authors.xlsx`.

In either case, the script will prompt you for the following:

- the starting date to gather publications (the default is the first of the
  current month),
- the ending date (default is the end of the current month)
- the Smartsheet sheet ID where your author list is stored (only if using
  Smartsheet; see above for how to obtain this number if you are)
- the department for which to provide results (default is blank, which disables
  filtering).
    - this filters the authors' "Primary Department" field by the value
      specified returning results just for the matching authors

After you've entered the values, the script will start running and produce
output like the following:

```
--- Starting the PMC crawler with the following parameters:
* START_DATE: 2023/02/01
* END_DATE: 2023/02/28
* AUTHORS_SHEET_ID: XXX
* AUTHORS_SHEET_PATH: YYY
* DEPARTMENT: 
---
Input Notebook:  Create Cites from PMC Lookups - Monthly.ipynb
Output Notebook: /app/_output/Create Cites from PMC Lookups - Monthly.ipynb
Executing notebook with kernel: python3
Executing Cell 1---------------------------------------
Ending Cell 1------------------------------------------
Executing Cell 2---------------------------------------
Ending Cell 2------------------------------------------
Executing Cell 3---------------------------------------

...

Executing Cell 40--------------------------------------
Read in /app/_build/cites_monthly-2023-02-28.md, outputted to /app/_build/cites_monthly-2023-02-28.pdf

Ending Cell 40-----------------------------------------
Executing Cell 41--------------------------------------
Read in /app/_build/cites_monthly-2023-02-28.md, outputted to /app/_build/cites_monthly-2023-02-28.docx

Ending Cell 41-----------------------------------------
Executing Cell 42--------------------------------------
Ending Cell 42-----------------------------------------

real    0m40.265s
user    0m0.043s
sys     0m0.026s
```

### Results

The results of the run are stored in the folder `output`, under a subfolder for
the given start and end date you specified. For example, if you specified
'2023/01/01' to '2023/01/31', the resulting output folder would be
`./output/2023-01-01_to_2023-01-31`.

You'll find the following files there, where `YYYY-MM-DD` will be the end date
you gave when you started the crawl:
- `cites_monthly-YYYY-MM-DD.pdf`, a PDF report of publications by authors in the
  input sheet
- `cites_monthly-YYYY-MM-DD.docx`, a Word document with the same formatting as
  the PDF
- `cites_monthly-YYYY-MM-DD.md`, a Markdown-formatted document with the same
  formatting as the PDF
- `cites_monthly-YYYY-MM-DD.xlsx`, an Excel spreadsheet containing the same data
  as the reports
