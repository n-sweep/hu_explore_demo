import streamlit as st
from streamlit_poc.clinical_trial_protocol_extractor.extractor_core import

st.title('Streamlit POC')

upload_tab, viewer_tab, chat_tab = st.tabs(['Upload', 'Data View', 'Explore Chat'])

with upload_tab:
    st.header('Upload PDF(s)')

    uploaded_pdfs = st.file_uploader("Upload files", accept_multiple_files=True)

    for pdf in uploaded_pdfs:  # type: ignore
        st.write(f'file uploaded: {pdf.name}')

with viewer_tab:
    st.header('Data Viewer')

with chat_tab:
    st.header('Explore Chat')

    st.chat_input("Your message")

