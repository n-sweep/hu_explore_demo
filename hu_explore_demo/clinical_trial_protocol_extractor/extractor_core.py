import os
import json
import sys
import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom
from openai import OpenAI
import tempfile
import argparse
import logging
import re
import subprocess
from typing import Dict, Any, List, Optional, Tuple
import docling
from docling.document_converter import DocumentConverter

#Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

api_key = os.environ.get("API_KEY")
if not api_key:
    raise ValueError("API_KEY environment variable not set")

client = OpenAI(api_key=api_key)


def extract_text_from_pdf(pdf_path: str) -> str:

    logger.info("Extracting text from PDF using docling DocumentConverter...")

    try:
        try:

            logger.info(f"Converting PDF with DocumentConverter: {pdf_path}")
            converter = DocumentConverter()
            result = converter.convert(pdf_path)

            # Export to markdown
            text = result.document.export_to_markdown()
            logger.info("Successfully converted PDF to markdown")
            return text
        except Exception as converter_error:
            logger.error(f"DocumentConverter failed: {converter_error}")
            raise

    except Exception as e:
        logger.error(f"All docling methods failed: {e}")


def chunk_text(text: str) -> List[str]:
    """
    Break text into manageable chunks while preserving section context
    it is using a larger chunk size (16000 estimated tokens) but still breaks up very large documents
    """
    if not isinstance(text, str):
        logger.error(f"chunk_text received non-string input: {type(text)}")
        text = str(text)

    section_pattern = r'(#{1,6}\s+.+?(?:\n|$))'

    try:
        sections = re.split(section_pattern, text, flags=re.MULTILINE)
    except Exception as e:
        logger.error(f"Error splitting text into sections: {e}")
        # Fallback to simple chunking
        return [text[i:i+64000] for i in range(0, len(text), 64000)]

    chunks = []
    current_chunk = []
    current_length = 0
    max_chunk_size = 64000

    for i in range(0, len(sections)):
        section = sections[i]
        if not section.strip():
            continue

        section_length = len(section)

        if current_length + section_length > max_chunk_size and current_chunk:
            chunks.append('\n'.join(current_chunk))
            current_chunk = [section]
            current_length = section_length
        else:
            current_chunk.append(section)
            current_length += section_length

    if current_chunk:
        chunks.append('\n'.join(current_chunk))

    if not chunks:
        logger.warning("Chunking produced no chunks, adding the whole text as one chunk")
        if len(text) > max_chunk_size:
            return [text[i:i+max_chunk_size] for i in range(0, len(text), max_chunk_size)]
        else:
            chunks = [text]

    logger.info(f"Split document into {len(chunks)} chunks")
    return chunks

#prompt gpt
def query_gpt(prompt: str, model: str = "gpt-4o", temperature: float = 0.0) -> str:
    try:
        # Limit the maximum token output
        response = client.chat.completions.create(model=model,
        messages=[
            {"role": "system", "content": "You are a protocol analyzer that helps extract structured information from clinical trial protocols. Always return valid JSON when requested, with no explanations or apologies."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=4096,
        temperature=temperature)
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error querying GPT: {e}")
        return "Error in GPT query"


def target_specific_field(content: str, field_name: str, field_type: str, context: str = "") -> Any:
    """
    Extract a specific field with targeted prompting

    Args:
        content: The text content to extract from
        field_name: The name of the field to extract
        field_type: The type of the field (string, array, full text, etc.)
        context: Additional context about where to find the info

    Returns:
        The extracted field value in the appropriate format
    """
    specific_prompt = f"""
    Extract the {field_name} from this clinical trial protocol text.

    {context}

    Return ONLY the exact {field_type} content of the {field_name}, with no additional text, explanations, or commentary.
    Return the information VERBATIM as it appears in the document, not summarized.
    If the information is not found, respond with "NOT_FOUND".

    Here is the text:
    {content}
    """

    response = query_gpt(specific_prompt)

    if response == "NOT_FOUND" or response == "Error in GPT query":
        return None

    # Handle different return types
    if field_type == "string":
        return response.strip()
    elif field_type == "array":
        try:
            # Try to parse as JSON array
            return json.loads(response)
        except json.JSONDecodeError:
            # If not valid JSON, split by newlines or commas
            if '\n' in response:
                return [item.strip() for item in response.split('\n') if item.strip()]
            else:
                return [item.strip() for item in response.split(',') if item.strip()]
    elif field_type == "boolean":
        response = response.lower().strip()
        return response in ["yes", "true", "y", "1"]
    elif field_type == "full_text":
        return response
    else:
        return response


def extract_eligibility_criteria(content: str) -> Dict[str, Any]:
    """
    Special handling for eligibility criteria which is particularly challenging
    """
    #find the sections containing inclusion/exclusion criteria
    criteria_prompt = """
    Find and extract the EXACT and COMPLETE eligibility criteria section from this clinical trial protocol.
    Include ALL inclusion criteria and ALL exclusion criteria with EXACT text and formatting.
    Do not summarize or paraphrase. Extract the VERBATIM text as it appears.
    List all criteria (both inclusion and exclusion) exactly as shown in the document, including all bullet points and numbering.

    Return ONLY the exact criteria text with no additional explanations or commentary.
    """

    criteria_text = query_gpt(criteria_prompt + "\n\nDocument text:\n" + content)

    # Default values in case extraction fails
    result = {
        "criteria": criteria_text if criteria_text != "Error in GPT query" and not criteria_text.startswith("I'm sorry") else "Not provided",
        "gender": "All",
        "minimum_age": "18 Years",
        "maximum_age": "N/A",
        "healthy_volunteers": "No"
    }

    if criteria_text == "Error in GPT query" or criteria_text.startswith("I'm sorry"):
        return result

    criteria_details_prompt = """
    Based on the eligibility criteria below, extract these specific details:

    Return ONLY a JSON object with these fields:
    - gender: The gender requirement ("All", "Female", or "Male")
    - minimum_age: The minimum age with units (e.g., "18 Years")
    - maximum_age: The maximum age with units or "N/A" if no limit
    - healthy_volunteers: Whether healthy volunteers are eligible ("Yes" or "No")

    Do not include any text outside the JSON object.

    Here are the criteria:
    """

    criteria_details = query_gpt(criteria_details_prompt + "\n" + criteria_text)

    try:
        json_start = criteria_details.find('{')
        if json_start > 0:
            criteria_details = criteria_details[json_start:]

        json_end = criteria_details.rfind('}')
        if json_end > 0 and len(criteria_details) > json_end + 1:
            criteria_details = criteria_details[:json_end+1]

        details = json.loads(criteria_details)

        if "gender" in details and details["gender"] in ["All", "Female", "Male"]:
            result["gender"] = details["gender"]

        if "minimum_age" in details:
            result["minimum_age"] = details["minimum_age"]

        if "maximum_age" in details:
            result["maximum_age"] = details["maximum_age"]

        if "healthy_volunteers" in details and details["healthy_volunteers"] in ["Yes", "No"]:
            result["healthy_volunteers"] = details["healthy_volunteers"]
    except json.JSONDecodeError:
        logger.warning("Failed to parse eligibility criteria details, using default values")

    return result


def extract_outcomes(content: str, outcome_type: str) -> List[Dict[str, str]]:
    """
    Extract primary or secondary outcomes with special handling
    """
    outcomes_prompt = f"""
    Your task is to extract all {outcome_type} outcome measures from this clinical trial protocol.

    YOU MUST format your response as a valid JSON array, with each outcome as an object having these exact fields:
    - outcome_measure: string
    - outcome_time_frame: string
    - outcome_description: string

    If you cannot find any {outcome_type} outcomes, return an empty array: []

    DO NOT include any explanations, apologies, or text outside the JSON array.

    Here is the text:
    {content}
    """

    outcomes_result = query_gpt(outcomes_prompt)
    if outcomes_result == "Error in GPT query":
        return []

    try:
        json_start = outcomes_result.find('[')
        if json_start > 0:
            outcomes_result = outcomes_result[json_start:]

        json_end = outcomes_result.rfind(']')
        if json_end > 0 and len(outcomes_result) > json_end + 1:
            outcomes_result = outcomes_result[:json_end+1]

        outcomes = json.loads(outcomes_result)
        return outcomes
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse {outcome_type} outcomes JSON, trying alternative extraction")

        try:
            #find out   how many outcomes there are
            count_prompt = f"""
            How many distinct {outcome_type} outcome measures are explicitly defined in this clinical trial protocol?
            Return only a single number (e.g., "3"). If none are found, return "0".
            DO NOT include any other text, explanations, or apologies.
            """
            outcome_count = query_gpt(count_prompt).strip()

            outcome_count = ''.join(c for c in outcome_count if c.isdigit())

            if not outcome_count:
                logger.warning(f"Could not determine number of {outcome_type} outcomes")
                return []

            count = int(outcome_count)
            logger.info(f"Attempting to extract {count} {outcome_type} outcomes individually")

            outcomes = []
            for i in range(1, count + 1):
                # Extract each field with a focused prompt
                measure_prompt = f"""
                What is the exact name or title of {outcome_type} outcome measure #{i} in this protocol?
                Return ONLY the name/title text with no additional explanation.
                """
                measure = query_gpt(measure_prompt).strip()

                time_frame_prompt = f"""
                What is the time frame specified for {outcome_type} outcome measure #{i} (titled: {measure}) in this protocol?
                Return ONLY the time frame with no additional explanation.
                """
                time_frame = query_gpt(time_frame_prompt).strip()

                description_prompt = f"""
                What is the full description of how {outcome_type} outcome measure #{i} (titled: {measure}) is assessed in this protocol?
                Return ONLY the description with no additional explanation.
                """
                description = query_gpt(description_prompt).strip()

                if measure and not measure.startswith("I'm sorry") and not measure.startswith("I don't"):
                    outcome = {
                        "outcome_measure": measure,
                        "outcome_time_frame": time_frame if not time_frame.startswith("I") else "Not specified",
                        "outcome_description": description if not description.startswith("I") else "Not specified"
                    }
                    outcomes.append(outcome)

            return outcomes
        except Exception as e:
            logger.warning(f"{outcome_type} outcomes extraction failed: {e}")
            return []


def extract_clinical_info(text_chunks: List[str]) -> Dict[str, Any]:
    """
    Extract clinical trial information from PDF text chunks using GPT-4o
    Uses targeted extraction for each field to improve accuracy
    """
    clinical_info = {}

    if not text_chunks:
        logger.error("No text chunks to process")
        text_chunks = ["Empty protocol document"]

    logger.info(f"Processing {len(text_chunks)} chunks of text")

    main_chunk = text_chunks[0] if len(text_chunks) > 0 else ""
    full_text = "\n\n".join(text_chunks[:min(3, len(text_chunks))])
    sections_prompt = """
    You are analyzing a clinical trial protocol document. Identify where the following sections are located:

    1. Title and basic info (beginning of document)
    2. Study design and phase information
    3. Eligibility criteria (inclusion/exclusion)
    4. Primary outcomes
    5. Secondary outcomes
    6. Arm groups/interventions
    7. Sponsor information

    For each section, provide the section name and whether it appears to be in the beginning, middle, or end of the document.
    Format as JSON with section_name and location fields.
    """

    section_info = query_gpt(sections_prompt + "\n\nHere's the beginning of the document:\n" + main_chunk)

    # Try to parse section info
    try:
        section_locations = json.loads(section_info)
        logger.info(f"Successfully identified document structure")
    except:
        logger.warning("Could not parse document structure, using default approach")
        section_locations = {}

    # Basic study information - critical fields
    logger.info("Extracting basic study information")
    title_prompt = """
    Extract the EXACT official title and brief title of this clinical trial protocol.

    Return ONLY a JSON object with these fields:
    - brief_title: The short title of the study (usually shorter)
    - official_title: The full, complete title of the study (usually longer)
    - acronym: The study acronym or abbreviation if present (or null if none)

    Do not include any text outside the JSON object.
    """

    title_info = query_gpt(title_prompt + "\n\nDocument text:\n" + main_chunk)

    try:
        title_data = json.loads(title_info)
        clinical_info["brief_title"] = title_data.get("brief_title", "Unknown Title")
        clinical_info["official_title"] = title_data.get("official_title", "Unknown Official Title")
        if title_data.get("acronym"):
            clinical_info["acronym"] = title_data.get("acronym")
    except:
        logger.warning("Failed to parse title information, falling back to field-by-field extraction")
        # Fallback to individual extraction
        clinical_info["brief_title"] = target_specific_field(
            main_chunk,
            "brief title (short title) of the study",
            "string",
            "This is usually at the beginning of the protocol."
        ) or "Unknown Title"

        clinical_info["official_title"] = target_specific_field(
            main_chunk,
            "official title (full title) of the study",
            "string",
            "This is usually at the beginning of the protocol and may be longer than the brief title."
        ) or "Unknown Official Title"

        clinical_info["acronym"] = target_specific_field(
            main_chunk,
            "study acronym or abbreviation",
            "string",
            "This may appear near the title."
        )

    clinical_info["org_study_id"] = target_specific_field(
        full_text,
        "organization's unique study identifier or protocol number",
        "string",
        "This is often a code or number that identifies the study within the organization."
    ) or "UNKNOWN_ID"

    # Study type and phase (critical for XML structure)
    logger.info("Extracting study design information")
    design_prompt = """
    Extract the study type and phase information from this clinical trial protocol.

    Return ONLY a JSON object with these fields:
    - study_type: Either "Interventional", "Observational", or "Expanded Access"
    - phase: The study phase (e.g., "Phase 1", "Phase 2", "Phase 1/2", "N/A", etc.)
    - primary_purpose: For interventional studies, the primary purpose (e.g., "Treatment", "Prevention", etc.)

    Do not include any text outside the JSON object.
    """

    design_info = query_gpt(design_prompt + "\n\nDocument text:\n" + full_text)

    try:
        design_data = json.loads(design_info)
        study_type = design_data.get("study_type", "Interventional")
        phase = design_data.get("phase")
        primary_purpose = design_data.get("primary_purpose")
    except:
        logger.warning("Failed to parse study design information, falling back to field-by-field extraction")
        study_type = target_specific_field(
            full_text,
            "study type",
            "string",
            "This should be one of: 'Interventional', 'Observational', or 'Expanded Access'."
        ) or "Interventional"

        phase = target_specific_field(
            full_text,
            "study phase",
            "string",
            "For example: 'Phase 1', 'Phase 2', 'Phase 3', 'Phase 4', 'Phase 1/2', etc."
        )

        primary_purpose = target_specific_field(
            full_text,
            "primary purpose of the study",
            "string",
            "For interventional studies, this could be: Treatment, Prevention, Diagnostic, etc."
        )

    # Create study design structure
    clinical_info["study_design"] = {
        "study_type": study_type  # Default to Interventional if not found
    }

    # Add more fields based on study type
    if study_type == "Interventional" or not study_type:
        interventional_fields = {}

        interventional_fields["interventional_subtype"] = primary_purpose or "Treatment"
        interventional_fields["phase"] = phase or "N/A"

        assignment = target_specific_field(
            full_text,
            "study design/interventional study model",
            "string",
            "This could be: Single Group Assignment, Parallel Assignment, Crossover Assignment, etc."
        )

        if assignment:
            interventional_fields["assignment"] = assignment

        allocation = target_specific_field(
            full_text,
            "allocation method",
            "string",
            "This should be one of: 'Randomized', 'Non-randomized', or 'N/A'."
        )

        interventional_fields["allocation"] = allocation or "N/A"

        # Simplified masking extraction - use a single powerful prompt
        masking_prompt = """
        Extract the masking/blinding information from this clinical trial protocol.

        Return ONLY a JSON object with these fields:
        - no_masking: "yes" if the study has no masking/blinding, "no" if it has some form of masking
        - masked_subject: "yes" if subjects are masked/blinded, "no" if not (if applicable)
        - masked_caregiver: "yes" if caregivers are masked/blinded, "no" if not (if applicable)
        - masked_investigator: "yes" if investigators are masked/blinded, "no" if not (if applicable)
        - masked_assessor: "yes" if outcome assessors are masked/blinded, "no" if not (if applicable)
        - description: A description of how masking was performed (if applicable)

        Only include fields that are relevant and can be determined from the protocol.
        """

        masking_result = query_gpt(masking_prompt + "\n\nDocument text:\n" + full_text)

        try:
            masking_info = json.loads(masking_result)
            if masking_info:
                interventional_fields["masking"] = masking_info
        except:
            logger.warning("Failed to parse masking information")

        clinical_info["study_design"]["interventional_design"] = interventional_fields

    elif study_type == "Observational":
        observational_fields = {}

        # Use a single comprehensive prompt for observational study details
        obs_prompt = """
        Extract the key details for this observational study.

        Return ONLY a JSON object with these fields:
        - observational_study_design: The model (e.g., "Cohort", "Case-Control", "Case-Only", etc.)
        - timing: The time perspective (e.g., "Retrospective", "Prospective", "Cross-Sectional", etc.)
        - biospecimen_retention: Whether biospecimens are retained (e.g., "None Retained", "Samples With DNA", etc.)
        - biospecimen_description: Description of biospecimens (if applicable)
        - number_of_groups: Number of groups/cohorts being studied
        - patient_registry: "yes" if this is a patient registry, "no" if not

        Only include fields that are relevant and can be determined from the protocol.
        """

        obs_result = query_gpt(obs_prompt + "\n\nDocument text:\n" + full_text)

        try:
            obs_data = json.loads(obs_result)
            if obs_data:
                observational_fields = obs_data
        except:
            logger.warning("Failed to parse observational study details")
            # Fallback to minimal fields
            observational_fields["observational_study_design"] = "Other"
            observational_fields["timing"] = "Other"
            observational_fields["biospecimen_retention"] = "None Retained"
            observational_fields["number_of_groups"] = "1"

        clinical_info["study_design"]["observational_design"] = observational_fields

    # Find eligibility criteria section - try different chunks if needed
    logger.info("Extracting eligibility criteria")
    eligibility_chunk = None

    # Try to identify which chunk has eligibility information based on headers
    for chunk_idx, chunk in enumerate(text_chunks):
        if "eligibility" in chunk.lower() or "inclusion criteria" in chunk.lower() or "exclusion criteria" in chunk.lower():
            eligibility_chunk = chunk
            logger.info(f"Found eligibility criteria in chunk {chunk_idx+1}")
            break

    # If not found, use the full text
    if not eligibility_chunk:
        logger.info("Could not find specific eligibility section, using full text")
        eligibility_chunk = full_text

    # Extract eligibility criteria with special handling
    eligibility_data = extract_eligibility_criteria(eligibility_chunk)
    clinical_info["eligibility"] = eligibility_data

    # Extract outcomes - find the most relevant chunk for each
    logger.info("Extracting outcomes information")
    outcome_chunk = None
    for chunk_idx, chunk in enumerate(text_chunks):
        if "outcome" in chunk.lower() or "endpoint" in chunk.lower() or "efficacy" in chunk.lower():
            outcome_chunk = chunk
            logger.info(f"Found outcomes in chunk {chunk_idx+1}")
            break

    if not outcome_chunk:
        outcome_chunk = full_text

    # Extract primary and secondary outcomes
    primary_outcomes = extract_outcomes(outcome_chunk, "primary")
    if primary_outcomes:
        clinical_info["primary_outcomes"] = primary_outcomes

    secondary_outcomes = extract_outcomes(outcome_chunk, "secondary")
    if secondary_outcomes:
        clinical_info["secondary_outcomes"] = secondary_outcomes

    # Extract arm groups with improved prompting
    logger.info("Extracting arm groups")
    arm_groups_prompt = """
    Extract all study arms/groups from this clinical trial protocol.

    Return ONLY a JSON array where each object has these fields:
    - arm_group_label: The name or label of the arm/group
    - arm_type: The type of arm (e.g., "Experimental", "Active Comparator", "Placebo Comparator", etc.)
    - arm_group_description: A description of what happens in this arm

    If you cannot find arm group information, return an empty array: []

    Do not include any text outside the JSON array.
    """

    # Try to identify the chunk with arm information
    arm_chunk = None
    for chunk_idx, chunk in enumerate(text_chunks):
        if "arm" in chunk.lower() or "group" in chunk.lower() or "treatment" in chunk.lower():
            arm_chunk = chunk
            logger.info(f"Found arm groups in chunk {chunk_idx+1}")
            break

    if not arm_chunk:
        arm_chunk = full_text

    arm_groups_result = query_gpt(arm_groups_prompt + "\n\nDocument text:\n" + arm_chunk)

    try:
        # Check if the response starts with explanatory text
        json_start = arm_groups_result.find('[')
        if json_start > 0:
            arm_groups_result = arm_groups_result[json_start:]

        # Check if the response has trailing text after JSON
        json_end = arm_groups_result.rfind(']')
        if json_end > 0 and len(arm_groups_result) > json_end + 1:
            arm_groups_result = arm_groups_result[:json_end+1]

        arm_groups = json.loads(arm_groups_result)
        if arm_groups:
            clinical_info["arm_groups"] = arm_groups
    except json.JSONDecodeError:
        logger.warning("Failed to parse arm groups JSON")

    # Extract interventions with improved prompting
    logger.info("Extracting interventions")
    interventions_prompt = """
    Extract all interventions from this clinical trial protocol.

    Return ONLY a JSON array where each object has these fields:
    - intervention_type: The type (e.g., "Drug", "Device", "Biological/Vaccine", etc.)
    - intervention_name: The name of the intervention
    - intervention_description: A description of the intervention
    - arm_group_label: Array of strings with names of arms that receive this intervention
    - intervention_other_name: Array of strings with alternative names (or empty array)

    If you cannot find intervention information, return an empty array: []

    Do not include any text outside the JSON array.
    """

    # Use the same chunk as arms if possible
    interventions_result = query_gpt(interventions_prompt + "\n\nDocument text:\n" + (arm_chunk or full_text))

    try:
        # Check if the response starts with explanatory text
        json_start = interventions_result.find('[')
        if json_start > 0:
            interventions_result = interventions_result[json_start:]

        # Check if the response has trailing text after JSON
        json_end = interventions_result.rfind(']')
        if json_end > 0 and len(interventions_result) > json_end + 1:
            interventions_result = interventions_result[:json_end+1]

        interventions = json.loads(interventions_result)
        if interventions:
            clinical_info["interventions"] = interventions
    except json.JSONDecodeError:
        logger.warning("Failed to parse interventions JSON")

    # Extract sponsors with improved prompting
    logger.info("Extracting sponsor information")
    sponsors_prompt = """
    Extract the sponsor information from this clinical trial protocol.

    Return ONLY a JSON object with these fields:
    - lead_sponsor: The organization name of the primary sponsor
    - collaborators: Array of organization names of any collaborators
    - responsible_party_type: Type (e.g., "Sponsor", "Principal Investigator", "Sponsor-Investigator")
    - investigator_title: Title of the investigator (if applicable)
    - investigator_affiliation: Affiliation of the investigator (if applicable)

    Only include fields that are present in the document.

    Do not include any text outside the JSON object.
    """

    sponsors_result = query_gpt(sponsors_prompt + "\n\nDocument text:\n" + main_chunk)

    try:
        sponsors_data = json.loads(sponsors_result)

        # Restructure to match expected format
        sponsors = {
            "lead_sponsor": sponsors_data.get("lead_sponsor", "UNKNOWN_SPONSOR")
        }

        if "collaborators" in sponsors_data:
            sponsors["collaborators"] = sponsors_data["collaborators"]

        # Create responsible party object if any relevant fields exist
        if any(key in sponsors_data for key in ["responsible_party_type", "investigator_title", "investigator_affiliation"]):
            resp_party = {}

            if "responsible_party_type" in sponsors_data:
                resp_party["resp_party_type"] = sponsors_data["responsible_party_type"]

            if "investigator_title" in sponsors_data:
                resp_party["investigator_title"] = sponsors_data["investigator_title"]

            if "investigator_affiliation" in sponsors_data:
                resp_party["investigator_affiliation"] = sponsors_data["investigator_affiliation"]

            sponsors["responsible_party"] = resp_party

        clinical_info["sponsors"] = sponsors
    except json.JSONDecodeError:
        logger.warning("Failed to parse sponsors JSON")
        # Fallback for critical lead sponsor information
        lead_sponsor = target_specific_field(
            main_chunk,
            "lead sponsor",
            "string",
            "What organization is the primary/lead sponsor of this study?"
        )
        if lead_sponsor:
            clinical_info["sponsors"] = {"lead_sponsor": lead_sponsor}

    # Extract remaining details with a comprehensive approach
    logger.info("Extracting study details (enrollment, status, dates, conditions)")
    details_prompt = """
    Extract these key study details from the clinical trial protocol.

    Return ONLY a JSON object with these fields:
    - enrollment: The target enrollment number (numeric value as string)
    - enrollment_type: "Anticipated" or "Actual"
    - overall_status: Study status (e.g., "Not yet recruiting", "Recruiting", "Completed")
    - start_date: Start date in YYYY-MM format
    - start_date_type: "Anticipated" or "Actual"
    - primary_compl_date: Primary completion date in YYYY-MM format
    - primary_compl_date_type: "Anticipated" or "Actual"
    - conditions: Array of strings with medical conditions being studied
    - keywords: Array of strings with relevant keywords

    Only include fields that you can find in the document. If information isn't available, omit the field.

    Do not include any text outside the JSON object.
    """

    details_result = query_gpt(details_prompt + "\n\nDocument text:\n" + full_text)

    try:
        details_data = json.loads(details_result)

        # Add each field if present
        for field in [
            "enrollment", "enrollment_type", "overall_status",
            "start_date", "start_date_type",
            "primary_compl_date", "primary_compl_date_type",
            "conditions", "keywords"
        ]:
            if field in details_data:
                clinical_info[field] = details_data[field]
    except json.JSONDecodeError:
        logger.warning("Failed to parse study details")

    # Extract summary information with improved prompting
    logger.info("Extracting study summary information")
    summary_prompt = """
    Extract the brief summary and detailed description of this clinical trial.

    Return ONLY a JSON object with these fields:
    - brief_summary: A brief summary of the study's purpose and approach (1-3 sentences)
    - detailed_description: A more detailed description of the study (if available)

    Only include fields that you can find in the document.

    Do not include any text outside the JSON object.
    """

    summary_result = query_gpt(summary_prompt + "\n\nDocument text:\n" + full_text)

    try:
        summary_data = json.loads(summary_result)

        if "brief_summary" in summary_data:
            clinical_info["brief_summary"] = summary_data["brief_summary"]

        if "detailed_description" in summary_data:
            clinical_info["detailed_description"] = summary_data["detailed_description"]
    except json.JSONDecodeError:
        logger.warning("Failed to parse summary information")

    return clinical_info


def generate_xml(clinical_info: Dict[str, Any]) -> str:
    """
    Generate XML conforming to the ClinicalTrials.gov schema
    """
    root = ET.Element("study_collection", xmlns="http://clinicaltrials.gov/prs")
    study = ET.SubElement(root, "clinical_study")

    id_info = ET.SubElement(study, "id_info")

    # Organization name and study ID are required
    org_name = ET.SubElement(id_info, "org_name")
    org_name.text = clinical_info.get("org_name", "UNKNOWN_ORG")

    org_study_id = ET.SubElement(id_info, "org_study_id")
    org_study_id.text = clinical_info.get("org_study_id", "UNKNOWN_ID")

    # Add titles
    if "brief_title" in clinical_info:
        brief_title = ET.SubElement(study, "brief_title")
        brief_title.text = clinical_info["brief_title"]

    if "official_title" in clinical_info:
        official_title = ET.SubElement(study, "official_title")
        official_title.text = clinical_info["official_title"]

    if "acronym" in clinical_info:
        acronym = ET.SubElement(study, "acronym")
        acronym.text = clinical_info["acronym"]

    # Add sponsors
    if "sponsors" in clinical_info:
        sponsors = ET.SubElement(study, "sponsors")

        # Lead sponsor is required
        lead_sponsor = ET.SubElement(sponsors, "lead_sponsor")
        agency = ET.SubElement(lead_sponsor, "agency")
        agency.text = clinical_info["sponsors"].get("lead_sponsor", "UNKNOWN_SPONSOR")

        # Add collaborators if present
        if "collaborators" in clinical_info["sponsors"]:
            for collab in clinical_info["sponsors"]["collaborators"]:
                collaborator = ET.SubElement(sponsors, "collaborator")
                collab_agency = ET.SubElement(collaborator, "agency")
                collab_agency.text = collab

        # Add responsible party if present
        if "responsible_party" in clinical_info["sponsors"]:
            resp_party = ET.SubElement(sponsors, "resp_party")

            resp_party_type = ET.SubElement(resp_party, "resp_party_type")
            resp_party_type.text = clinical_info["sponsors"]["responsible_party"].get("resp_party_type", "Sponsor")

            # Add investigator details if responsible party is an investigator
            if "investigator_title" in clinical_info["sponsors"]["responsible_party"]:
                inv_title = ET.SubElement(resp_party, "investigator_title")
                inv_title.text = clinical_info["sponsors"]["responsible_party"]["investigator_title"]

            if "investigator_affiliation" in clinical_info["sponsors"]["responsible_party"]:
                inv_affil = ET.SubElement(resp_party, "investigator_affiliation")
                inv_affil.text = clinical_info["sponsors"]["responsible_party"]["investigator_affiliation"]

    # Study type and design
    study_design = ET.SubElement(study, "study_design")

    study_type = ET.SubElement(study_design, "study_type")
    study_type.text = clinical_info.get("study_design", {}).get("study_type", "Interventional")

    # Add interventional design if applicable
    if study_type.text == "Interventional" and "interventional_design" in clinical_info.get("study_design", {}):
        int_design = ET.SubElement(study_design, "interventional_design")
        int_design_data = clinical_info["study_design"]["interventional_design"]

        # Add required fields
        subtype = ET.SubElement(int_design, "interventional_subtype")
        subtype.text = int_design_data.get("interventional_subtype", "Treatment")

        phase = ET.SubElement(int_design, "phase")
        phase.text = int_design_data.get("phase", "N/A")

        if "assignment" in int_design_data:
            assignment = ET.SubElement(int_design, "assignment")
            assignment.text = int_design_data["assignment"]

        allocation = ET.SubElement(int_design, "allocation")
        allocation.text = int_design_data.get("allocation", "N/A")

        # Handle masking
        if "masking" in int_design_data:
            masking_data = int_design_data["masking"]

            if "no_masking" in masking_data:
                no_masking = ET.SubElement(int_design, "no_masking")
                no_masking.text = masking_data["no_masking"]

            for role in ["subject", "caregiver", "investigator", "assessor"]:
                masked_key = f"masked_{role}"
                if masked_key in masking_data:
                    masked_elem = ET.SubElement(int_design, masked_key)
                    masked_elem.text = masking_data[masked_key]

            if "description" in masking_data:
                masking_desc = ET.SubElement(int_design, "masking_description")
                textblock = ET.SubElement(masking_desc, "textblock")
                textblock.text = masking_data["description"]

    # Add observational design if applicable
    elif study_type.text == "Observational" and "observational_design" in clinical_info.get("study_design", {}):
        obs_design = ET.SubElement(study_design, "observational_design")
        obs_design_data = clinical_info["study_design"]["observational_design"]

        # Add required fields
        obs_study_design = ET.SubElement(obs_design, "observational_study_design")
        obs_study_design.text = obs_design_data.get("observational_study_design", "Other")

        timing = ET.SubElement(obs_design, "timing")
        timing.text = obs_design_data.get("timing", "Other")

        biospec_retention = ET.SubElement(obs_design, "biospecimen_retention")
        biospec_retention.text = obs_design_data.get("biospecimen_retention", "None Retained")

        if "biospecimen_description" in obs_design_data:
            biospec_desc = ET.SubElement(obs_design, "biospecimen_description")
            textblock = ET.SubElement(biospec_desc, "textblock")
            textblock.text = obs_design_data["biospecimen_description"]

        num_groups = ET.SubElement(obs_design, "number_of_groups")
        num_groups.text = obs_design_data.get("number_of_groups", "1")

        if "patient_registry" in obs_design_data:
            patient_reg = ET.SubElement(obs_design, "patient_registry")
            patient_reg.text = obs_design_data["patient_registry"]

            if obs_design_data["patient_registry"] == "yes":
                if "target_duration_quantity" in obs_design_data:
                    target_dur_qty = ET.SubElement(obs_design, "target_duration_quantity")
                    target_dur_qty.text = obs_design_data["target_duration_quantity"]

                if "target_duration_units" in obs_design_data:
                    target_dur_units = ET.SubElement(obs_design, "target_duration_units")
                    target_dur_units.text = obs_design_data["target_duration_units"]

    # Add eligibility criteria
    if "eligibility" in clinical_info:
        eligibility_data = clinical_info["eligibility"]
        eligibility = ET.SubElement(study, "eligibility")

        # Add criteria
        criteria = ET.SubElement(eligibility, "criteria")
        textblock = ET.SubElement(criteria, "textblock")
        textblock.text = eligibility_data.get("criteria", "Not provided")

        # Add gender
        gender = ET.SubElement(eligibility, "gender")
        gender.text = eligibility_data.get("gender", "All")

        # Add healthy volunteers
        if "healthy_volunteers" in eligibility_data:
            healthy_vol = ET.SubElement(eligibility, "healthy_volunteers")
            healthy_vol.text = eligibility_data["healthy_volunteers"].lower()

        # Add minimum and maximum age
        min_age = ET.SubElement(eligibility, "minimum_age")
        min_age.text = eligibility_data.get("minimum_age", "18 Years")

        max_age = ET.SubElement(eligibility, "maximum_age")
        max_age.text = eligibility_data.get("maximum_age", "N/A")

    # Add outcomes
    if "primary_outcomes" in clinical_info:
        for outcome in clinical_info["primary_outcomes"]:
            primary_outcome = ET.SubElement(study, "primary_outcome")

            outcome_measure = ET.SubElement(primary_outcome, "outcome_measure")
            outcome_measure.text = outcome.get("outcome_measure", "")

            if "outcome_time_frame" in outcome:
                time_frame = ET.SubElement(primary_outcome, "outcome_time_frame")
                time_frame.text = outcome["outcome_time_frame"]

            if "outcome_description" in outcome:
                desc = ET.SubElement(primary_outcome, "outcome_description")
                textblock = ET.SubElement(desc, "textblock")
                textblock.text = outcome["outcome_description"]

    if "secondary_outcomes" in clinical_info:
        for outcome in clinical_info["secondary_outcomes"]:
            secondary_outcome = ET.SubElement(study, "secondary_outcome")

            outcome_measure = ET.SubElement(secondary_outcome, "outcome_measure")
            outcome_measure.text = outcome.get("outcome_measure", "")

            if "outcome_time_frame" in outcome:
                time_frame = ET.SubElement(secondary_outcome, "outcome_time_frame")
                time_frame.text = outcome["outcome_time_frame"]

            if "outcome_description" in outcome:
                desc = ET.SubElement(secondary_outcome, "outcome_description")
                textblock = ET.SubElement(desc, "textblock")
                textblock.text = outcome["outcome_description"]

    # Add enrollment
    if "enrollment" in clinical_info:
        enrollment = ET.SubElement(study, "enrollment")
        enrollment.text = clinical_info["enrollment"]

        if "enrollment_type" in clinical_info:
            enrollment_type = ET.SubElement(study, "enrollment_type")
            enrollment_type.text = clinical_info["enrollment_type"]

    # Add conditions
    if "conditions" in clinical_info:
        for condition in clinical_info["conditions"]:
            condition_elem = ET.SubElement(study, "condition")
            condition_elem.text = condition

    # Add keywords
    if "keywords" in clinical_info:
        for keyword in clinical_info["keywords"]:
            keyword_elem = ET.SubElement(study, "keyword")
            keyword_elem.text = keyword

    # Add arm groups
    if "arm_groups" in clinical_info:
        for arm in clinical_info["arm_groups"]:
            arm_group = ET.SubElement(study, "arm_group")

            arm_label = ET.SubElement(arm_group, "arm_group_label")
            arm_label.text = arm.get("arm_group_label", "")

            if "arm_type" in arm:
                arm_type = ET.SubElement(arm_group, "arm_type")
                arm_type.text = arm["arm_type"]

            if "arm_group_description" in arm:
                arm_desc = ET.SubElement(arm_group, "arm_group_description")
                textblock = ET.SubElement(arm_desc, "textblock")
                textblock.text = arm["arm_group_description"]

    # Add interventions
    if "interventions" in clinical_info:
        for intervention in clinical_info["interventions"]:
            intervention_elem = ET.SubElement(study, "intervention")

            if "intervention_type" in intervention:
                int_type = ET.SubElement(intervention_elem, "intervention_type")
                int_type.text = intervention["intervention_type"]

            int_name = ET.SubElement(intervention_elem, "intervention_name")
            int_name.text = intervention.get("intervention_name", "")

            if "intervention_description" in intervention:
                int_desc = ET.SubElement(intervention_elem, "intervention_description")
                textblock = ET.SubElement(int_desc, "textblock")
                textblock.text = intervention["intervention_description"]

            # Add arm group labels
            if "arm_group_label" in intervention:
                for label in intervention["arm_group_label"]:
                    arm_label = ET.SubElement(intervention_elem, "arm_group_label")
                    arm_label.text = label

            # Add other names
            if "intervention_other_name" in intervention:
                for other_name in intervention["intervention_other_name"]:
                    other_name_elem = ET.SubElement(intervention_elem, "intervention_other_name")
                    other_name_elem.text = other_name

    # Add study status and dates
    for field in ["overall_status", "start_date", "start_date_type",
                 "primary_compl_date", "primary_compl_date_type",
                 "last_follow_up_date", "last_follow_up_date_type"]:
        if field in clinical_info:
            field_elem = ET.SubElement(study, field)
            field_elem.text = clinical_info[field]

    # Add brief and detailed description
    if "brief_summary" in clinical_info:
        brief_summary = ET.SubElement(study, "brief_summary")
        textblock = ET.SubElement(brief_summary, "textblock")
        textblock.text = clinical_info["brief_summary"]

    if "detailed_description" in clinical_info:
        detailed_desc = ET.SubElement(study, "detailed_description")
        textblock = ET.SubElement(detailed_desc, "textblock")
        textblock.text = clinical_info["detailed_description"]

    # Convert to string with proper formatting
    rough_string = ET.tostring(root, encoding='utf-8')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ")


def process_pdf_to_xml(pdf_path: str, output_xml_path: str = None) -> str:
    """
    Process a PDF file to XML conforming to ClinicalTrials.gov schema
    """
    try:
        logger.info(f"Extracting text from PDF: {pdf_path}")
        pdf_text = extract_text_from_pdf(pdf_path)

        logger.info("Processing text")
        text_chunks = chunk_text(pdf_text)

        logger.info(f"Extracting clinical information from {len(text_chunks)} chunks of text")
        clinical_info = extract_clinical_info(text_chunks)

        logger.info("Generating XML")
        xml_content = generate_xml(clinical_info)

        if output_xml_path:
            with open(output_xml_path, 'w', encoding='utf-8') as f:
                f.write(xml_content)
            logger.info(f"XML saved to: {output_xml_path}")

        return xml_content

    except Exception as e:
        logger.error(f"Error processing PDF: {str(e)}", exc_info=True)

        root = ET.Element("study_collection", xmlns="http://clinicaltrials.gov/prs")
        study = ET.SubElement(root, "clinical_study")

        id_info = ET.SubElement(study, "id_info")
        org_name = ET.SubElement(id_info, "org_name")
        org_name.text = "ERROR_PROCESSING"

        org_study_id = ET.SubElement(id_info, "org_study_id")
        org_study_id.text = os.path.basename(pdf_path).replace(".pdf", "")

        brief_title = ET.SubElement(study, "brief_title")
        brief_title.text = f"Error processing {os.path.basename(pdf_path)}"

        error_desc = ET.SubElement(study, "detailed_description")
        error_textblock = ET.SubElement(error_desc, "textblock")
        error_textblock.text = f"Error during processing: {str(e)}"

        # Convert to string
        rough_string = ET.tostring(root, encoding='utf-8')
        reparsed = minidom.parseString(rough_string)
        xml_content = reparsed.toprettyxml(indent="  ")

        if output_xml_path:
            with open(output_xml_path, 'w', encoding='utf-8') as f:
                f.write(xml_content)
            logger.info(f"Minimal XML saved to: {output_xml_path} due to error: {e}")

        return xml_content


#Main method
def main():
    parser = argparse.ArgumentParser(description='Convert Clinical Trial Protocol PDF to XML')
    parser.add_argument('pdf_path', help='Path to the PDF file')
    parser.add_argument('--output', '-o', help='Output XML file path')

    args = parser.parse_args()


    output_path = args.output
    if not output_path:
        # Create default output path based on input filename
        pdf_base = os.path.splitext(os.path.basename(args.pdf_path))[0]
        output_path = f"{pdf_base}_protocol.xml"

    try:
        xml_content = process_pdf_to_xml(args.pdf_path, output_path)
        print(f"Successfully converted {args.pdf_path} to {output_path}")
    except Exception as e:
        logger.error(f"Unhandled error in main: {e}")
        print(f"Error processing PDF: {e}")


if __name__ == "__main__":
    main()
