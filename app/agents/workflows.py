"""Demonstration of Sequential, Parallel, and Loop Agent Workflows in Google ADK."""

from google.adk.agents import Agent, SequentialAgent, ParallelAgent, LoopAgent
from app.agents.llm import get_llm
from app.agents.tools import (
    get_patient_documents, read_document, get_appointment_history,
    prepare_consultation_summary
)

llm = get_llm()

# =====================================================================
# 1. SEQUENTIAL WORKFLOW (PRD Section 27.1)
# Document processing pipeline: Extraction -> Validation -> Summary
# =====================================================================

extractor_agent = Agent(
    model=llm,
    name="document_extractor_agent",
    description="Extracts raw clinical and laboratory values from medical documents.",
    instruction="Extract all raw medical terms, lab metrics, and patient details verbatim from the document.",
    tools=[get_patient_documents, read_document]
)

validator_agent = Agent(
    model=llm,
    name="document_validator_agent",
    description="Validates extracted metrics against standard reference ranges.",
    instruction="Cross-check extracted numbers against normal biological ranges and note any flagged abnormal values."
)

synthesizer_agent = Agent(
    model=llm,
    name="document_synthesizer_agent",
    description="Produces a patient-friendly summary from validated clinical data.",
    instruction="Provide a compassionate, plain-English summary of the findings and advise discussion with a physician."
)

document_sequential_workflow = SequentialAgent(
    name="document_processing_pipeline",
    sub_agents=[
        extractor_agent,
        validator_agent,
        synthesizer_agent
    ]
)


# =====================================================================
# 2. PARALLEL WORKFLOW (PRD Section 27.2)
# Multi-source consultation prep: History + Documents in parallel, then report
# =====================================================================

parallel_history_fetcher = Agent(
    model=llm,
    name="parallel_history_fetcher",
    description="Fetches patient appointment history.",
    instruction="Fetch all past appointment dates and diagnoses.",
    tools=[get_appointment_history]
)

parallel_document_fetcher = Agent(
    model=llm,
    name="parallel_document_fetcher",
    description="Fetches recent medical documents.",
    instruction="Fetch all uploaded medical documents and lab reports.",
    tools=[get_patient_documents]
)

parallel_data_gatherer = ParallelAgent(
    name="parallel_data_gatherer",
    sub_agents=[
        parallel_history_fetcher,
        parallel_document_fetcher
    ]
)

final_brief_compiler = Agent(
    model=llm,
    name="final_brief_compiler",
    description="Compiles collected history and documents into a doctor briefing sheet.",
    instruction="Synthesize the parallel inputs into an organized consultation preparation brief.",
    tools=[prepare_consultation_summary]
)

consultation_prep_workflow = SequentialAgent(
    name="consultation_prep_workflow",
    sub_agents=[
        parallel_data_gatherer,
        final_brief_compiler
    ]
)


# =====================================================================
# 3. LOOP WORKFLOW (PRD Section 27.3)
# Iterative quality checking
# =====================================================================

draft_generator = Agent(
    model=llm,
    name="draft_generator",
    instruction="Generate or refine a patient consultation summary draft based on available patient data."
)

safety_reviewer = Agent(
    model=llm,
    name="safety_reviewer",
    instruction="Review the draft to ensure no autonomous diagnoses or medication changes were recommended."
)

summary_refinement_loop = LoopAgent(
    name="summary_refinement_loop",
    sub_agents=[
        draft_generator,
        safety_reviewer
    ],
    max_iterations=2
)
