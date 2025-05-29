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
from dotenv import load_dotenv
import pandas as pd
from pyathena import connect

pd.options.display.width = 1000
BUCKET = 'hu-explorer-demo'
load_dotenv()


# %%
s3 = boto3.client('s3')
s3.list_buckets()

# %%
# con = connect()
query = """
SELECT *
FROM ci4cc_hackathon_database.clinical_onco_patient
LIMIT 10
"""
df = pd.read_sql(query, con)
df

# %%
bucket = boto3.resource('s3').Bucket(BUCKET)
for obj in bucket.objects.all():
    print(obj.key, obj.size)

# %%
bucket = boto3.resource('s3').Bucket(BUCKET)
for obj in bucket.objects.all():
    if obj.key.endswith('xml'):
        # s3.delete_object(Bucket=BUCKET, Key=obj.key)
        print(obj.key)


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
