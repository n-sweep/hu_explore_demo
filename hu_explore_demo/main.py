import os
import boto3
import logging
import tempfile
import pandas as pd
import streamlit as st

from openai import OpenAI
from dotenv import load_dotenv
from io import BytesIO, StringIO

from botocore.client import BaseClient
from typing import Callable

# [TODO]: unable to run locally; uncomment this block to complete the upload pipeline
# from clinical_trial_protocol_extractor.extractor_core import process_pdf_to_xml

logging.basicConfig(filename='test.log', level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()


if not (api_key:=os.environ.get("API_KEY")):
    raise ValueError("API_KEY environment variable not set")

BUCKET = 'hu-explorer-demo'
S3_CLIENT = boto3.client('s3')
OPENAI_CLIENT = OpenAI(api_key=api_key)


### prompts#####################################################################

DATA_VIEWER_SYSTEM_PROMPT = """You a data analyizer/synthesizer. The user will
provide a prompt they wish to be applied to each row in a table of clinical
trial data, creating a new column of responses across that table. You will be
given a single row of data from that table and you will provide an appropriate
response that will be used as content in this new column. Provide only this
content with no additional explanation or apology."""

DATA_VIEWER_ROWWISE_PROMPT = """
# Row Data

```
{}
```

---

# User Prompt

{}
"""

EXPLORE_SYSTEM_PROMPT = """You are an accurate and truthful data analyst and
assistant. Below is a table of data. Respond to the prompts with regards to the
data to the best of your ability. Admit when you don't know something.

# Table Data

```
{}
```
"""

### helper functions############################################################


def s3_file_exists(client: BaseClient, bucket: str, key: str) -> bool:
    """Check if a key exists in a given bucket"""
    try:
        client.head_object(Bucket=bucket, Key=key)

        return True

    except client.exceptions.ClientError as e:

        if e.response['Error']['Code'] == '404':
            return False
        else:
            raise


@st.cache_data
def s3_load_trials_csv(_client: BaseClient, _bucket: str, _key: str = 'table/clinical_trials.csv') -> pd.DataFrame:
    """Load the clinical trials table from s3"""

    response = _client.get_object(Bucket=_bucket, Key=_key)
    csv_data = response['Body'].read().decode('utf-8')

    return pd.read_csv(StringIO(csv_data))


def query_gpt(
    client: OpenAI,
    prompt: str|None = None,
    system_prompt: str|None = None,
    messages: list[dict]|None = None,
    model: str = 'gpt-4o',
    temperature: float = 0.0
) -> str:

    if prompt and system_prompt:
        messages = [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': prompt}
            ]
    elif not messages:
        raise ValueError("ERROR: Either a prompt and system prompt or a list of messages must be provided")

    try:
        # Limit the maximum token output
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=4096,
            temperature=temperature
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error querying GPT: {e}")
        return "Error in GPT query"


def gpt_generate_data_viewer_apply_func(client: OpenAI, user_prompt: str) -> Callable:

    def func(row: pd.Series) -> str:
        prompt = DATA_VIEWER_ROWWISE_PROMPT.format(str(row), user_prompt)
        response = query_gpt(client, prompt, DATA_VIEWER_SYSTEM_PROMPT)
        st.markdown(f"`[{row.name}]`**: {row['file_name']}**  \n{response}  \n")

        return response

    return func


### streamlit ##################################################################

st.set_page_config(layout='wide')
st.title('Clinical Trial Upload/Explore Demo')

upload_tab, viewer_tab, chat_tab = st.tabs(['Upload', 'Data View', 'Explore Chat'])


### streamlit uploads ##########################################################

with upload_tab:
    st.header('Upload PDF(s)')

    uploaded_pdfs = st.file_uploader("Upload files", accept_multiple_files=True)

    for pdf in uploaded_pdfs:
        raw_key = f'raw/{pdf.name}'
        xml_key = f'processed/{pdf.name.replace('.pdf', '.xml')}'

        if s3_file_exists(S3_CLIENT, BUCKET, raw_key):
            st.write(f'File already exists: {pdf.name}')
        else:
            S3_CLIENT.upload_fileobj(pdf, BUCKET, raw_key)
            st.write(f'File uploaded: {pdf.name}')

        if not s3_file_exists(S3_CLIENT, BUCKET, xml_key):

            # [TODO]: unable to run locally; uncomment this block to complete the upload pipeline
            # with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as tmp_file:
            #     tmp_file.write(pdf.read())
            #     xml_str = process_pdf_to_xml(tmp_file.name, 'test.xml')

            # xml_bytes = xml_str.encode("utf-8")
            # buffer = BytesIO(xml_bytes)

            # S3_CLIENT.upload_fileobj(buffer, BUCKET, xml_key)

            ...


### streamlit data viewer ######################################################

with viewer_tab:
    st.header('Data Viewer')

    df = s3_load_trials_csv(S3_CLIENT, BUCKET)

    st.subheader('Search & Sort')

    search_col, sort_col, filter_col = st.columns([1, 1, 1])

    with search_col:
        with st.expander('Text Search'):
            search = st.text_input("Search all fields...")
            if search:
                mask = df.apply(lambda x: x.astype(str).str.contains(search, case=False).any(), axis=1)
                df = df[mask]

    with sort_col:
        with st.expander('Sort options'):
            sort_col = st.selectbox('Sort by', df.columns, key='sort_col')
            sort_order = st.radio('Order', ['Ascending', 'Descending'], horizontal=True, key='sort_order')
            df = df.sort_values(by=sort_col, ascending=(sort_order == 'Ascending'))

    with filter_col:
        with st.expander('Filter columns'):
            for col in df.select_dtypes(include='object').columns:
                unique_vals = df[col].dropna().unique().tolist()
                if len(unique_vals) < 100:  # don't auto-filter huge cardinality columns
                    selected_vals = st.multiselect(f"Filter `{col}`", unique_vals, default=unique_vals, key=f"filter_{col}")
                    df = df[df[col].isin(selected_vals)]

    st.subheader('Chat')
    st_chat = st.empty()

    st.divider()

    st_data = st.empty()
    st_data.dataframe(df)

    if usr_input:=st_chat.chat_input("Generate a response for each row in the table..."):
        func = gpt_generate_data_viewer_apply_func(OPENAI_CLIENT, usr_input)
        timestamp = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
        st.markdown(f'# Chat {timestamp}  \n```{usr_input}```')
        df[timestamp] = df.apply(func, axis=1)
        st_data.dataframe(df)


### streamlit explore chat #####################################################

with chat_tab:

    st.header('Explore Chat')
    df = s3_load_trials_csv(S3_CLIENT, BUCKET)

    st.subheader('Data')
    with st.expander('Expand Table', expanded=True):
        st.dataframe(df)

    if 'messages' not in st.session_state:
        system_prompt = EXPLORE_SYSTEM_PROMPT.format(str(df))
        st.session_state.messages = [{'role': 'system', 'content': system_prompt}]

    if st.session_state.get('pending_response', False):
        response = query_gpt(OPENAI_CLIENT, messages=st.session_state.messages)
        st.session_state.messages.append({'role':'assistant', 'content': response})
        st.session_state.pending_response = False
        st.rerun()

    st.divider()

    st.subheader('Chat')

    for message in st.session_state.messages:
        if (role:=message['role']) != 'system':
            with st.chat_message(role):
                st.markdown(message['content'])

    if usr_input:=st.chat_input('Ask questions about this table...'):
        st.session_state.messages.append({'role':'user', 'content': usr_input})
        st.session_state.pending_response = True
        st.rerun()

