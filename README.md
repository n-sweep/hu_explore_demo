# Project Plan: Explore Streamlit Demo

## Objective

Build a Streamlit app for Explore that supports secure upload of clinical trial PDFs, extracts and stores structured data, and enables interactive exploration of the data.

## Overview

The app will have three main tabs:

1. Upload – Upload and process PDF files, extract structured data, and store results in S3.
2. Data Viewer – Tabular view of all extracted clinical trial data (from a cumulative CSV).
3. Explore Chat – OpenAI chat interface to search across all processed data using Athena.

---

### Tab 1: Upload

#### Features

- Upload PDF files (multiple allowed).
- Optional password input to restrict access (not S3 credentials).
- For each uploaded file:
    1. Check if the file already exists in s3://<bucket>/raw/
    2. If it does not exist:
- Upload to raw
- Process using the clinical trial extractor (reuse code from Kinal’s app)
- Extract:
    - Summary (text)
    - Structured form data (dict/JSON)
- Store in processed/<filename>/:
    - summary.txt
    - form_data.json
    - raw.pdf
- Append the extracted form_data as a row in a master CSV:
    - Located at s3://<bucket>/table/trials.csv
    - Each row = one trial (flattened version of form_data JSON + filename)

---

### Tab 2: Data Viewer

#### Features

- Use pyathena to load trials.csv from s3://<bucket>/table/.
- Display as a dynamic table in Streamlit:
    - Search, sort, and filter.
    - Columns = flattened keys from the clinical trial form data + filename + summary
- Option to download a row as JSON or view summary.txt.

---

### Tab 3: Explore Chat

##### Features

- OpenAI-powered chat interface (e.g., st.chat_input()).
    - Supports semantic questions like:
        - "Which trials require patients to be over 65?"
        - "Find trials studying melanoma sponsored by Merck."
    - Queries should be translated to SQL over Athena or matched via semantic search over summary + structured form fields.

---

### S3 Structure

s3://<bucket>/
├── raw/
│   └── trial1.pdf, trial2.pdf, ...
├── processed/
│   └── trial1/
│       ├── raw.pdf
│       ├── summary.txt
│       └── form_data.json
├── table/
│   └── trials.csv  <-- cumulative table, updated on every upload


---

### Security

- Add simple password input to Streamlit sidebar or upload tab.
- Use os.getenv() for AWS credentials (never hardcode keys).
- IAM role or env-secured access to S3.

---

Attached is a outside app S3 key, it should give you access to a data folder. It does not have write access just yet but I'll modify it later so you can write into a new bucket.

Information on how the key was being used before, might not be entirely relevant for you: https://docs.healthuniverse.com/ci4cc-hackathon-database

There is no code repo so far, feel free to make your own but you can look at this repo for the processing of the data. We don't need to do more than this is already doing:

https://github.com/Health-Universe/HealthUniverse_clinical_trial_protocol_extractor

Some example data is also attached. I will move it into an S3 once I'm home in about 3 hours
