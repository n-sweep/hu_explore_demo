# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: hydrogen
#       format_version: '1.3'
#       jupytext_version: 1.16.6
#   kernelspec:
#     display_name: Python3
#     language: python
#     name: Python3
# ---

# %% [markdown]
# # Template Notebook

# %%
import os
import boto3
import pandas as pd
from io import StringIO
from dotenv import load_dotenv
from pyathena import connect
from openai import OpenAI

from typing import Callable

pd.options.display.width = 1000

BUCKET = 'hu-explorer-demo'

DATA_VIEWER_SYSTEM_PROMPT = """You a data analyizer/synthesizer. The user will
provide a prompt they wish to be applied to each row in a table of clinical
trial data, creating a new column of responses across that table. You will be
given a single row of data from that table and you will provide an appropriate
response that will be used as content in this new column. Provide only this
content with no additional explanation or apology."""

DATA_VIEWER_ROWWISE_PROMPT = """
# User Prompt

{}

---  

# Row Data

```
{}
```
"""

load_dotenv()

s3 = boto3.client('s3')

api_key = os.environ.get("API_KEY")
if not api_key:
    raise ValueError("API_KEY environment variable not set")

client = OpenAI(api_key=api_key)


# %%
def s3_load_trials_csv(_client, _bucket, _key='table/clinical_trials.csv') -> pd.DataFrame:
    """Load the clinical trials table from s3"""

    response = _client.get_object(Bucket=_bucket, Key=_key)
    csv_data = response['Body'].read().decode('utf-8')

    return pd.read_csv(StringIO(csv_data))


def query_gpt(prompt: str, system_prompt: str, model: str = "gpt-4o", temperature: float = 0.0) -> str:
    try:
        # Limit the maximum token output
        response = client.chat.completions.create(model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        max_tokens=4096,
        temperature=temperature)
        return response.choices[0].message.content.strip()
    except Exception as e:
        # logger.error(f"Error querying GPT: {e}")
        return "Error in GPT query"


def generate_data_viewer_gpt_apply_func(user_prompt: str) -> Callable:

    def func(row_data: str) -> str:
        prompt = DATA_VIEWER_ROWWISE_PROMPT.format(user_prompt, row_data)
        return query_gpt(prompt, DATA_VIEWER_SYSTEM_PROMPT)

    return func



# %%
df = s3_load_trials_csv(s3, BUCKET)
prompt = 'hello this is a test'
row_data = str(df.iloc[0])

res = data_viewer_query_gpt(prompt, row_data)
print(res)


# %%
bucket = boto3.resource('s3').Bucket(BUCKET)
for obj in bucket.objects.all():
    print(obj.key, obj.size)

# %%
response = s3.get_object(Bucket=BUCKET, Key='table/clinical_trials.csv')
csv_data = response['Body'].read().decode('utf-8')
df = pd.read_csv(StringIO(csv_data))
df

# %%
bucket = boto3.resource('s3').Bucket(BUCKET)
for obj in bucket.objects.all():
    if obj.key.endswith('xml'):
        # s3.delete_object(Bucket=BUCKET, Key=obj.key)
        print(obj.key)


# %%
con = connect()
query = """
SELECT *
FROM ci4cc_hackathon_database.clinical_onco_patient
LIMIT 10
"""
df = pd.read_sql(query, con)
df

# %%
# %%
# %%
# %%
# %%
# %%
# %%
# %%
# %%
# %%
# %%
# %%
# %%
# %%
# %%
# %%
