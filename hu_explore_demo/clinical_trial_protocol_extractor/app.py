import streamlit as st
import os
from tempfile import NamedTemporaryFile
from extractor_core import (
    extract_text_from_pdf,
    chunk_text,
    extract_clinical_info,
    generate_xml
)

st.set_page_config(page_title="Clinical Trial Protocol Extractor", layout="wide")

with open( "style.css" ) as css:
    st.markdown( f'<style>{css.read()}</style>' , unsafe_allow_html= True)

# Title
st.title("Clinical Trial Protocol Extractor")

#Instructions
with st.expander("**Instructions**"):
    st.markdown("""    
    This application converts clinical trial protocol PDFs into structured XML data compatible with ClinicalTrials.gov submissions.
    
    **How to use:**
    1. **Upload** your clinical trial protocol PDF using the file uploader above
    2. **Review** the extracted information in each category (Titles, Study Design, etc.)
    3. **Edit** any fields that need correction or additional information
    4. **Generate XML** using the button at the bottom to create and download the formatted XML file
    
    **Tips:**
    - The app uses AI to extract information, but always review for accuracy
    - Expand each section to see and edit specific protocol details
    - All fields can be edited if the AI extraction needs correction
    - For list fields (like Collaborators), use commas to separate multiple items
    
    **Output:**
    The generated XML file follows ClinicalTrials.gov schema and can be used for submission after review.
    """)
    
# disclaimer

with st.expander("**Disclaimer**"):
    st.markdown("""
    This tool uses AI to extract information from clinical trial protocols and should be used for assistance only, not as a replacement for professional review. The accuracy of extracted data depends on the quality and format of the uploaded document. Always thoroughly review all generated content before submission.
    """)

st.divider()

# Initialize session state for all data if not exists
if "clinical_info" not in st.session_state:
    st.session_state.clinical_info = {}

# File uploader
uploaded_file = st.file_uploader("**Upload Clinical Trial PDF**", type=["pdf"], help="Upload your clinical trial protocol pdf file.")

if uploaded_file:
    # Create a fingerprint of the uploaded file for comparison
    file_fingerprint = uploaded_file.name + str(uploaded_file.size)
    
    # Check if this is a new file by comparing fingerprints
    if "file_fingerprint" not in st.session_state or st.session_state.file_fingerprint != file_fingerprint:
        st.session_state.file_fingerprint = file_fingerprint
        
        with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(uploaded_file.read())
            pdf_path = tmp_file.name
            
        st.success(f"Uploaded: {uploaded_file.name}")
        
        with st.spinner("Extracting clinical trial info..."):
            try:
                pdf_text = extract_text_from_pdf(pdf_path)
                chunks = chunk_text(pdf_text)
                st.session_state.clinical_info = extract_clinical_info(chunks)
                st.session_state.pdf_path = pdf_path
            except Exception as e:
                st.error(f"Error extracting info: {e}")
                st.stop()
    
    # Make editable fields grouped in expanders
    with st.expander("📄 Titles"):
        st.session_state.clinical_info["brief_title"] = st.text_input(
            "Brief Title",
            value=st.session_state.clinical_info.get("brief_title", ""),
            key="brief_title"
        )
        st.session_state.clinical_info["official_title"] = st.text_area(
            "Official Title",
            value=st.session_state.clinical_info.get("official_title", ""),
            key="official_title"
        )
        st.session_state.clinical_info["acronym"] = st.text_input(
            "Acronym",
            value=st.session_state.clinical_info.get("acronym", ""),
            key="acronym"
        )

    with st.expander("📐 Study Design"):
        study_type = st.session_state.clinical_info.get("study_design", {}).get("study_type", "")
        st.text(f"Study Type: {study_type}")
        
        # Ensure the nested dictionary structure exists
        if "study_design" not in st.session_state.clinical_info:
            st.session_state.clinical_info["study_design"] = {"study_type": study_type}
            
        if study_type == "Interventional":
            if "interventional_design" not in st.session_state.clinical_info["study_design"]:
                st.session_state.clinical_info["study_design"]["interventional_design"] = {}
                
            design = st.session_state.clinical_info["study_design"]["interventional_design"]
            
            st.session_state.clinical_info["study_design"]["interventional_design"]["interventional_subtype"] = st.text_input(
                "Subtype",
                value=design.get("interventional_subtype", ""),
                key="interventional_subtype"
            )
            
            st.session_state.clinical_info["study_design"]["interventional_design"]["phase"] = st.text_input(
                "Phase",
                value=design.get("phase", ""),
                key="phase"
            )
            
            st.session_state.clinical_info["study_design"]["interventional_design"]["assignment"] = st.text_input(
                "Assignment",
                value=design.get("assignment", ""),
                key="assignment"
            )
            
            st.session_state.clinical_info["study_design"]["interventional_design"]["allocation"] = st.text_input(
                "Allocation",
                value=design.get("allocation", ""),
                key="allocation"
            )
            
        elif study_type == "Observational":
            if "observational_design" not in st.session_state.clinical_info["study_design"]:
                st.session_state.clinical_info["study_design"]["observational_design"] = {}
                
            design = st.session_state.clinical_info["study_design"]["observational_design"]
            
            st.session_state.clinical_info["study_design"]["observational_design"]["observational_study_design"] = st.text_input(
                "Study Design",
                value=design.get("observational_study_design", ""),
                key="observational_study_design"
            )
            
            st.session_state.clinical_info["study_design"]["observational_design"]["timing"] = st.text_input(
                "Timing",
                value=design.get("timing", ""),
                key="timing"
            )
            
            st.session_state.clinical_info["study_design"]["observational_design"]["biospecimen_retention"] = st.text_input(
                "Biospecimen Retention",
                value=design.get("biospecimen_retention", ""),
                key="biospecimen_retention"
            )
            
            st.session_state.clinical_info["study_design"]["observational_design"]["number_of_groups"] = st.text_input(
                "# Groups",
                value=design.get("number_of_groups", ""),
                key="number_of_groups"
            )

    with st.expander("🧬 Eligibility"):
        if "eligibility" not in st.session_state.clinical_info:
            st.session_state.clinical_info["eligibility"] = {}
            
        elig = st.session_state.clinical_info["eligibility"]
        
        st.session_state.clinical_info["eligibility"]["criteria"] = st.text_area(
            "Eligibility Criteria",
            value=elig.get("criteria", ""),
            key="eligibility_criteria"
        )
        
        st.session_state.clinical_info["eligibility"]["gender"] = st.text_input(
            "Gender",
            value=elig.get("gender", ""),
            key="gender"
        )
        
        st.session_state.clinical_info["eligibility"]["minimum_age"] = st.text_input(
            "Min Age",
            value=elig.get("minimum_age", ""),
            key="minimum_age"
        )
        
        st.session_state.clinical_info["eligibility"]["maximum_age"] = st.text_input(
            "Max Age",
            value=elig.get("maximum_age", ""),
            key="maximum_age"
        )
        
        st.session_state.clinical_info["eligibility"]["healthy_volunteers"] = st.text_input(
            "Healthy Volunteers",
            value=elig.get("healthy_volunteers", ""),
            key="healthy_volunteers"
        )

    with st.expander("🎯 Outcomes"):
        st.markdown("**Primary Outcomes**")
        
        if "primary_outcomes" not in st.session_state.clinical_info:
            st.session_state.clinical_info["primary_outcomes"] = []
            
        for i, outcome in enumerate(st.session_state.clinical_info.get("primary_outcomes", [])):
            st.session_state.clinical_info["primary_outcomes"][i]["outcome_measure"] = st.text_input(
                f"Primary Measure {i+1}",
                value=outcome.get("outcome_measure", ""),
                key=f"primary_measure_{i}"
            )
            
            st.session_state.clinical_info["primary_outcomes"][i]["outcome_time_frame"] = st.text_input(
                f"Time Frame {i+1}",
                value=outcome.get("outcome_time_frame", ""),
                key=f"primary_timeframe_{i}"
            )
            
            st.session_state.clinical_info["primary_outcomes"][i]["outcome_description"] = st.text_area(
                f"Description {i+1}",
                value=outcome.get("outcome_description", ""),
                key=f"primary_description_{i}"
            )
            
        st.markdown("**Secondary Outcomes**")
        
        if "secondary_outcomes" not in st.session_state.clinical_info:
            st.session_state.clinical_info["secondary_outcomes"] = []
            
        for i, outcome in enumerate(st.session_state.clinical_info.get("secondary_outcomes", [])):
            st.session_state.clinical_info["secondary_outcomes"][i]["outcome_measure"] = st.text_input(
                f"Secondary Measure {i+1}",
                value=outcome.get("outcome_measure", ""),
                key=f"secondary_measure_{i}"
            )
            
            st.session_state.clinical_info["secondary_outcomes"][i]["outcome_time_frame"] = st.text_input(
                f"Time Frame {i+1}",
                value=outcome.get("outcome_time_frame", ""),
                key=f"secondary_timeframe_{i}"
            )
            
            st.session_state.clinical_info["secondary_outcomes"][i]["outcome_description"] = st.text_area(
                f"Description {i+1}",
                value=outcome.get("outcome_description", ""),
                key=f"secondary_description_{i}"
            )

    with st.expander("💊 Interventions & Arms"):
        if "arm_groups" not in st.session_state.clinical_info:
            st.session_state.clinical_info["arm_groups"] = []
            
        for i, arm in enumerate(st.session_state.clinical_info.get("arm_groups", [])):
            st.session_state.clinical_info["arm_groups"][i]["arm_group_label"] = st.text_input(
                f"Arm Group Label {i+1}",
                value=arm.get("arm_group_label", ""),
                key=f"arm_label_{i}"
            )
            
            st.session_state.clinical_info["arm_groups"][i]["arm_type"] = st.text_input(
                f"Arm Type {i+1}",
                value=arm.get("arm_type", ""),
                key=f"arm_type_{i}"
            )
            
            st.session_state.clinical_info["arm_groups"][i]["arm_group_description"] = st.text_area(
                f"Arm Description {i+1}",
                value=arm.get("arm_group_description", ""),
                key=f"arm_description_{i}"
            )
            
        if "interventions" not in st.session_state.clinical_info:
            st.session_state.clinical_info["interventions"] = []
            
        for i, intv in enumerate(st.session_state.clinical_info.get("interventions", [])):
            st.session_state.clinical_info["interventions"][i]["intervention_name"] = st.text_input(
                f"Intervention Name {i+1}",
                value=intv.get("intervention_name", ""),
                key=f"intervention_name_{i}"
            )
            
            st.session_state.clinical_info["interventions"][i]["intervention_type"] = st.text_input(
                f"Intervention Type {i+1}",
                value=intv.get("intervention_type", ""),
                key=f"intervention_type_{i}"
            )
            
            st.session_state.clinical_info["interventions"][i]["intervention_description"] = st.text_area(
                f"Intervention Description {i+1}",
                value=intv.get("intervention_description", ""),
                key=f"intervention_description_{i}"
            )

    with st.expander("🏢 Sponsor Info"):
        if "sponsors" not in st.session_state.clinical_info:
            st.session_state.clinical_info["sponsors"] = {}
            
        sponsor = st.session_state.clinical_info.get("sponsors", {})
        
        st.session_state.clinical_info["sponsors"]["lead_sponsor"] = st.text_input(
            "Lead Sponsor",
            value=sponsor.get("lead_sponsor", ""),
            key="lead_sponsor"
        )
        
        # Handle collaborators list as a comma-separated string
        collaborators_str = ", ".join(sponsor.get("collaborators", []))
        new_collaborators_str = st.text_area(
            "Collaborators",
            value=collaborators_str,
            key="collaborators"
        )
        
        # Convert back to list if changed
        if new_collaborators_str != collaborators_str:
            st.session_state.clinical_info["sponsors"]["collaborators"] = [
                item.strip() for item in new_collaborators_str.split(",") if item.strip()
            ]

    with st.expander("📆 Study Metadata"):
        st.session_state.clinical_info["org_study_id"] = st.text_input(
            "Org Study ID",
            value=st.session_state.clinical_info.get("org_study_id", ""),
            key="org_study_id"
        )
        
        st.session_state.clinical_info["enrollment"] = st.text_input(
            "Enrollment",
            value=st.session_state.clinical_info.get("enrollment", ""),
            key="enrollment"
        )
        
        st.session_state.clinical_info["enrollment_type"] = st.text_input(
            "Enrollment Type",
            value=st.session_state.clinical_info.get("enrollment_type", ""),
            key="enrollment_type"
        )
        
        st.session_state.clinical_info["overall_status"] = st.text_input(
            "Overall Status",
            value=st.session_state.clinical_info.get("overall_status", ""),
            key="overall_status"
        )
        
        st.session_state.clinical_info["start_date"] = st.text_input(
            "Start Date",
            value=st.session_state.clinical_info.get("start_date", ""),
            key="start_date"
        )
        
        st.session_state.clinical_info["primary_compl_date"] = st.text_input(
            "Primary Completion Date",
            value=st.session_state.clinical_info.get("primary_compl_date", ""),
            key="primary_compl_date"
        )
        
        # Handle conditions list as a comma-separated string
        conditions_str = ", ".join(st.session_state.clinical_info.get("conditions", []))
        new_conditions_str = st.text_area(
            "Conditions",
            value=conditions_str,
            key="conditions"
        )
        
        # Convert back to list if changed
        if new_conditions_str != conditions_str:
            st.session_state.clinical_info["conditions"] = [
                item.strip() for item in new_conditions_str.split(",") if item.strip()
            ]
        
        # Handle keywords list as a comma-separated string
        keywords_str = ", ".join(st.session_state.clinical_info.get("keywords", []))
        new_keywords_str = st.text_area(
            "Keywords",
            value=keywords_str,
            key="keywords"
        )
        
        # Convert back to list if changed
        if new_keywords_str != keywords_str:
            st.session_state.clinical_info["keywords"] = [
                item.strip() for item in new_keywords_str.split(",") if item.strip()
            ]

    with st.expander("📝 Study Summary"):
        st.session_state.clinical_info["brief_summary"] = st.text_area(
            "Brief Summary",
            value=st.session_state.clinical_info.get("brief_summary", ""),
            key="brief_summary"
        )
        
        st.session_state.clinical_info["detailed_description"] = st.text_area(
            "Detailed Description",
            value=st.session_state.clinical_info.get("detailed_description", ""),
            key="detailed_description"
        )

    # Final button to generate XML
    if st.button("Generate XML and Download"):
        with st.spinner("Generating XML..."):
            xml_string = generate_xml(st.session_state.clinical_info)
            st.download_button("📥 Download XML", data=xml_string, file_name="clinical_trial.xml", mime="text/xml")
            st.text_area("Preview XML", xml_string, height=300)



# ----Sidebar UI----
st.sidebar.markdown("""
<h2 style='color: black; margin-bottom: 0; font-size: 1em;'>Clinical Trial Protocol Extractor Overview</h2>
<p></p>
<p>The Clinical Trial Protocol Extractor app automates the conversion of clinical trial protocol PDFs into structured XML data compatible with 
<a href="https://clinicaltrials.gov/submit-studies/prs-help/user-guide#xml" target="_blank">ClinicalTrials.gov</a> submission standards. 
It uses AI to analyze protocols and extract essential information. The application presents the extracted data in an editable interface where users can review and modify the information before generating standardized XML output for regulatory submission. This tool significantly reduces the manual effort required to transform lengthy text-based protocols into structured data formats required by clinical trial registries.</p>
""", unsafe_allow_html=True)

st.sidebar.divider()

# Display the logo + feedback
st.sidebar.image("HU_Logo.svg", use_container_width="auto")
st.sidebar.write("**We value your feedback!** Please share your comments in our [discussions](https://www.healthuniverse.com/apps/Clinical%20Trial%20Protocol%20Extractor/discussions).")
