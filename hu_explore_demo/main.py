import boto3
import streamlit as st
from io import BytesIO
from dotenv import load_dotenv

load_dotenv()

from clinical_trial_protocol_extractor.extractor_core import process_pdf_to_xml


BUCKET = 'hu-explorer-demo'
s3_client = boto3.client('s3')


def s3_file_exists(client, bucket, key):
    try:
        client.head_object(Bucket=bucket, Key=key)

        return True

    except s3_client.exceptions.ClientError as e:

        if e.response['Error']['Code'] == "404":
            return False
        else:
            raise


st.title('Explore Demo')

upload_tab, viewer_tab, chat_tab = st.tabs(['Upload', 'Data View', 'Explore Chat'])


with upload_tab:
    st.header('Upload PDF(s)')

    uploaded_pdfs = st.file_uploader("Upload files", accept_multiple_files=True)

    for pdf in uploaded_pdfs:
        raw_key = f'raw/{pdf.name}'
        xml_key = f'processed/{pdf.name.replace('.pdf', '.xml')}'

        if s3_file_exists(s3_client, BUCKET, raw_key):
            st.write(f'File already exists: {raw_key}')
        else:
            # s3_client.upload_fileobj(pdf, BUCKET, raw_key)
            ...

        if not s3_file_exists(s3_client, BUCKET, xml_key):
            xml_str = process_pdf_to_xml(pdf.name, 'test.xml')
            xml_bytes = xml_str.encode("utf-8")
            buffer = BytesIO(xml_bytes)

            # s3_client.upload_fileobj(buffer, BUCKET, xml_key)

        break


with viewer_tab:
    st.header('Data Viewer')


with chat_tab:
    st.header('Explore Chat')

    st.chat_input("Your message")

