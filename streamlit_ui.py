import streamlit as st
import pandas as pd
from app.services.ranking_service import RankingService
from app.parsers.docx_parser import DocxParser
from app.parsers.pypdf_parser import PyPDFParser
from app.services.cleanup_service import CleanupService
from app.config.settings import Settings
from app.services.zoho_candidate_service import ZohoCandidateService
from app.services.fetch_openings import ZohoJobService
from app.services.get_sample_profiles import ZohoSampleProfileService
from app.services.zoho_auth import get_access_token, ZohoTokenError, ZohoRateLimitError
from app.services.fetch_openings import ZohoAPIError, ZohoNoDataError
import tempfile
import os
import logging
import shutil
import streamlit as st
TRACING_ENABLED = False
try:
    from phoenix.otel import register
    from openinference.instrumentation.openai import OpenAIInstrumentor

    # Set environment variables for Phoenix
    # os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"api_key={os.getenv('OTEL_EXPORTER_OTLP_HEADERS')}"
    # os.environ["PHOENIX_CLIENT_HEADERS"] = f"api_key={os.getenv('PHOENIX_CLIENT_HEADERS')}"
    # os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = os.getenv('PHOENIX_COLLECTOR_ENDPOINT')

    os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"api_key={st.secrets['OTEL_EXPORTER_OTLP_HEADERS']}"
    os.environ["PHOENIX_CLIENT_HEADERS"] = f"api_key={st.secrets['PHOENIX_CLIENT_HEADERS']}"
    os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = st.secrets['PHOENIX_COLLECTOR_ENDPOINT']

    try:
        tracer_provider = register(
            project_name="Profile Ranking System",
            endpoint=st.secrets['OTEL_EXPORTER_OTLP_ENDPOINT'],
            batch=True,
            auto_instrument=True
        )

        # Instrument OpenAI
        OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)
        TRACING_ENABLED = True
        logging.info("OpenTelemetry tracing initialized successfully")

    except Exception as e:
        logging.error("Failed to initialize OpenTelemetry tracing", exc_info=True)
        tracer_provider = None

except ImportError:
    logging.warning("Phoenix tracing packages not found, tracing disabled")
    tracer_provider = None
except Exception as e:
    logging.error("Unexpected error during tracing setup", exc_info=True)
    tracer_provider = None

CSS_STYLES = """
<style>
.stDownloadButton button {
    background-color: #fa4b4b;
    color: white;
    font-size: 16px;
    padding: 8px 16px;
    width: 100%;
    border: none;
    border-radius: 6px;
}
.stDownloadButton button:hover {
    background-color: #CC0000;
}
</style>    
"""

# Helper Functions
def save_uploaded_files(uploaded_files):
    """Save uploaded files to a temporary directory and return the directory path."""
    temp_dir = tempfile.mkdtemp()
    for uploaded_file in uploaded_files:
        file_path = os.path.join(temp_dir, uploaded_file.name)
        with open(file_path, "wb") as f:    
            f.write(uploaded_file.getbuffer())
    return temp_dir

def read_job_description(uploaded_file):
    """Read and extract text from uploaded job description file."""
    if uploaded_file is None:
        return ""
        
    file_extension = uploaded_file.name.split(".")[-1].lower()
    temp_dir = None
    temp_path = None
    
    try:
        if file_extension == "txt":
            return uploaded_file.getvalue().decode("utf-8")
            
        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, f"job_desc_temp.{file_extension}")
        
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getvalue())
            f.flush()
            os.fsync(f.fileno())

        if file_extension in ["doc", "docx"]:
            parser = DocxParser()
        elif file_extension == "pdf":
            parser = PyPDFParser()
        else:
            raise ValueError(f"Unsupported file extension: {file_extension}")
    
        result = parser.parse(temp_path)
        if not result or not result.get("content"):
            raise ValueError("Parser returned no content")
            
        return result["content"]
            
    except Exception as e:
        logging.error(f"Error reading file {uploaded_file.name}: {str(e)}")
        st.error(f"Error reading job description file: {str(e)}")
        return ""
    
    finally:
        CleanupService.cleanup_job_desc_files(temp_path, temp_dir)

def format_display_dataframe(df):
    """Format the display DataFrame with numeric formatting and additional columns"""
    df['total_score'] = df['total_score'].apply(lambda x: f"{x:.2f}")
    df['total_professional_experience'] = df['total_professional_experience'].apply(lambda x: f"{x:.1f}")
    df['total_relevant_experience'] = df['total_relevant_experience'].apply(lambda x: f"{x:.1f}")
    df['processing_time'] = df['processing_time'].apply(lambda x: f"{x:.2f}s")
    return df

def get_scoring_configuration():
    """
    Returns the scoring weights and priority order from the sidebar configuration.
    Handles the UI elements and validation for scoring configuration.
    Returns tuple: (scoring_weights, priority_order) or None if validation fails
    """
    st.sidebar.header("Scoring Configuration")
    st.sidebar.write("Adjust the weights for each scoring criterion (must sum to 100%).")

    skills_weight = st.sidebar.slider("Skills Match Weight (%)", 0, 100, 35)
    total_professional_experience_weight = st.sidebar.slider("Total Professional Experience Weight (%)", 0, 100, 15)
    total_relevant_experience_weight = st.sidebar.slider("Relevant Experience Weight (%)", 0, 100, 15)
    education_weight = st.sidebar.slider("Education Weight (%)", 0, 100, 15)
    certifications_weight = st.sidebar.slider("Certifications Weight (%)", 0, 100, 10)
    location_weight = st.sidebar.slider("Location Weight (%)", 0, 100, 10)

    total_weight = (
        skills_weight + total_professional_experience_weight +
        total_relevant_experience_weight + education_weight +
        certifications_weight + location_weight
    )

    if total_weight != 100:
        st.sidebar.error("Weights must sum to 100%. Please adjust the values.")
        return None

    st.sidebar.header("Tie-Breaking Priority")
    st.sidebar.write("Set the priority order for breaking ties between candidates with the same score.")

    priority_order = st.sidebar.multiselect(
        "Priority Order (drag to reorder):",
        options=["skills_match", "total_professional_experience", "total_relevant_experience",
                "education", "certifications", "location"],
        default=["skills_match", "total_relevant_experience", "total_professional_experience",
                "education", "certifications", "location"]
    )

    # Convert weights to decimal form (0-1 range)
    scoring_weights = {
        "skills_match": float(skills_weight) / 100,
        "total_professional_experience": float(total_professional_experience_weight) / 100,
        "total_relevant_experience": float(total_relevant_experience_weight) / 100,
        "education": float(education_weight) / 100,
        "certifications": float(certifications_weight) / 100,
        "location": float(location_weight) / 100
    }

    return scoring_weights, priority_order

def add_download_buttons(display_df, results_df):
    """Add download buttons for filtered and full rankings"""
    col1, col2 = st.columns(2)
    with col1:
        csv_filtered = display_df.to_csv(index=False)
        st.markdown('<div class="stDownloadButton">', unsafe_allow_html=True)
        st.download_button(
            label=f"📥 Download Filtered Rankings ({len(display_df)} candidates)",
            data=csv_filtered,
            file_name="filtered_rankings.csv",
            mime="text/csv",
            key="download_filtered"
        )
        st.markdown('</div>', unsafe_allow_html=True)
    with col2:
        csv_full = results_df.to_csv(index=False)
        st.markdown('<div class="stDownloadButton">', unsafe_allow_html=True)
        st.download_button(
            label=f"📥 Download All Rankings ({len(results_df)} candidates)",
            data=csv_full,
            file_name="all_rankings.csv",
            mime="text/csv",
            key="download_full"
        )
        st.markdown('</div>', unsafe_allow_html=True)

def get_column_config():
    """Return the column configuration for the results DataFrame"""
    return {
        'name': 'Name',
        'email': 'Email',
        'phone': 'Phone',
        'total_score': st.column_config.NumberColumn(
            'Total Score',
            format='%.2f',
            help='Overall match score (0-100)'
        ),
        'skills_match': st.column_config.NumberColumn(
            'Skills Match',
            format='%.2f',
            help='Match score for skills (0-100)'
        ),
        'total_professional_experience': st.column_config.NumberColumn(
            'Professional Exp (yrs)',
            format='%.1f',
            help='Total professional experience in years'
        ),
        'total_relevant_experience': st.column_config.NumberColumn(
            'Relevant Exp (yrs)',
            format='%.1f',
            help='Relevant experience in years'
        ),
        'education': st.column_config.NumberColumn(
            'Education',
            format='%.2f',
            help='Education match score (0-100)'
        ),
        'certifications': st.column_config.NumberColumn(
            'Certifications',
            format='%.2f',
            help='Certifications match score (0-100)'
        ),
        'location': st.column_config.NumberColumn(
            'Location',
            format='%.2f',
            help='Location match score (0-100)'
        ),
        'processing_time': st.column_config.TextColumn(
            'Processing Time',
            help='Time taken to process the resume'
        )
    }

def display_ranking_results(results_df, key_prefix=""):
    """Display ranking results in a formatted table with filters
    
    Args:
        results_df: DataFrame containing the ranking results
        key_prefix: Optional prefix to make widget keys unique when called multiple times
    """
    st.subheader("Rankings:")
    
    # Sort by total_score in descending order (highest first)
    results_df = results_df.sort_values('total_score', ascending=False)
    
    # Add a rank column starting from 1
    results_df['Rank'] = range(1, len(results_df) + 1)
    
    # Set rank as the first column
    column_order = ['Rank'] + [col for col in results_df.columns if col != 'Rank']
    results_df = results_df[column_order]
    
    # Add filter controls
    col1, col2 = st.columns(2)
    with col1:
        show_top_n = st.number_input(
            "Show Top N Candidates", 
            min_value=1, 
            max_value=len(results_df),
            value=len(results_df),
            key=f"show_top_n_{key_prefix}" if key_prefix else "show_top_n"
        )
    with col2:
        min_score = st.slider(
            "Minimum Score Filter",
            min_value=float(50),
            max_value=float(100),
            value=float(results_df['total_score'].min()),
            key=f"min_score_filter_{key_prefix}" if key_prefix else "min_score_filter"
        )

    # Apply filters
    display_df = results_df[results_df['total_score'] >= min_score].head(show_top_n)
    
    # Format display DataFrame
    display_df = format_display_dataframe(display_df)
    
    # Display results
    st.dataframe(
        display_df,
        column_config={
            'Rank': st.column_config.NumberColumn('Rank', format='%d'),
            **get_column_config()
        },
        hide_index=True,
        use_container_width=True,
        height=min(800, 100 + len(display_df) * 35)  # Dynamic height based on number of rows
    )
    
    add_download_buttons(display_df, results_df)

def process_manual_mode(model_choice):
    """Handle manual upload mode"""
    st.write("Upload resumes and job description to rank candidates.")
    
    job_desc_file = st.file_uploader(
        "Upload Job Description", 
        type=["txt", "doc", "docx", "pdf"]
    )

    uploaded_files = st.file_uploader(
        "Upload resumes to evaluate (PDF, DOC, DOCX)",
        type=["pdf", "doc", "docx"],
        accept_multiple_files=True,
        key="resumes"
    )
    
    good_resumes = st.file_uploader(
        "Upload sample good resumes (maximum 5 files)",
        type=["pdf", "doc", "docx"],
        accept_multiple_files=True,
        key="good_resumes"
    )

    if good_resumes and len(good_resumes) > 5:
        st.error("Please upload a maximum of 5 sample resumes.")
        good_resumes = good_resumes[:5]

    # Get scoring configuration once and store it
    scoring_config = get_scoring_configuration()
    if scoring_config is None:  # Validation failed
        return
    scoring_weights, priority_order = scoring_config
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("""
            <style>
            div.stButton > button {
                background-color: #fa4b4b;
                color: white;
                font-size: 16px;
                padding: 10px 16px;
                width: auto;
                margin: 0 auto;
                display: block;
                border: none;
                border-radius: 6px;
            }
            </style>
        """, unsafe_allow_html=True)
        
        if st.button("🔍 Rank Resumes", key="rank_button", use_container_width=True):
            if not uploaded_files:
                st.warning("Please upload at least one resume.")
                return
            
            if not job_desc_file:
                st.warning("Please upload a job description file.")
                return
                
            # Use the already validated scoring configuration
            if not scoring_config:
                st.warning("Please fix the scoring configuration in the sidebar.")
                return

            job_description = ""
            if job_desc_file:
                with st.spinner("Reading job description..."):
                    job_description = read_job_description(job_desc_file)
                    if not job_description:
                        st.error("Failed to read job description file. Please check the file and try again.")

            try:
                with st.spinner("Processing resumes..."):
                    temp_dir = save_uploaded_files(uploaded_files)
                    
                    if good_resumes:
                        num_resumes = len(good_resumes)
                        logging.info(f"Number of good sample resumes uploaded: {num_resumes}")
                        good_dir = save_uploaded_files(good_resumes)
                        logging.info(f"Good resumes saved to directory: {good_dir}")
                    else:
                        logging.info("No good sample resumes uploaded")
                        good_dir = None
                
                    
                    ranker = RankingService(
                        model=model_choice,
                        scoring_weights=scoring_weights,
                        ranking_priority=priority_order
                    )
                    
                    if good_dir:
                        logging.info("Analyzing good sample resumes...")
                        ranker.analyze_example_resumes(good_dir, job_description)
                        if not ranker.llm_service.good_characteristics:
                            st.warning("Failed to extract characteristics from good resumes")
                    
                    result = ranker.process_resumes(temp_dir, job_description)
                    
                    if 'error' in result:
                        if result.get('error_type') == 'INSUFFICIENT_QUOTA':
                            st.error("⚠️ OpenAI API quota exceeded. Please check your billing details and recharge your account.")
                        else:
                            st.error(f"An error occurred: {result['error']}")
                    elif 'data' in result and not result['data'].empty:
                        st.session_state.manual_results_df = result['data']
                    else:
                        st.error("No results were generated. Please check the uploaded files and try again.")
                    
                    CleanupService.cleanup_upload_dirs(temp_dir, good_dir)
                        
            except Exception as e:
                st.error(f"An error occurred: {str(e)}")
                logging.exception("Error in manual mode processing")

    if st.session_state.manual_results_df is not None:
        display_ranking_results(st.session_state.manual_results_df, key_prefix="manual")

def process_zoho_mode(model_choice):
    """Handle Zoho integration mode"""
    try:
        # Initialize session state for tracking new results if not exists
        if 'show_new_results' not in st.session_state:
            st.session_state.show_new_results = False
            
        zoho_job_service = None
        zoho_candidate_service = None
        temp_dir = None
        sample_dir = None

        try:
            zoho_job_service = ZohoJobService()
            # Initialize with higher concurrency for better performance
            zoho_candidate_service = ZohoCandidateService(max_concurrent_downloads=15)
            temp_dir = zoho_candidate_service.create_temp_dir()
        except Exception as e:
            logging.exception("Failed to initialize Zoho services")
            st.error("Failed to initialize Zoho integration. Please check your internet connection and try again.")
            return
        scoring_config = get_scoring_configuration()
        if scoring_config is None:  # Validation failed
            return
        scoring_weights, priority_order = scoring_config    
        if st.session_state.active_jobs is None:
            with st.spinner("Fetching job openings from Zoho Recruit..."):
                try:
                    active_jobs = zoho_job_service.get_active_job_openings()
                    if not active_jobs:
                        st.warning("No active job openings found in Zoho Recruit.")
                        return
                    st.session_state.active_jobs = active_jobs
                except ZohoTokenError as e:
                    st.error("❌ Authentication failed. Please check your Zoho API credentials and refresh token.")
                    logging.error(f"Zoho authentication error: {str(e)}")
                    return
                except ZohoRateLimitError as e:
                    st.error("⚠️ Zoho API rate limit reached. Please wait a few minutes and try again.")
                    logging.error(f"Zoho rate limit error: {str(e)}")
                    return
                except ZohoNoDataError:
                    st.warning("No active job openings found in Zoho Recruit.")
                    return
                except ZohoAPIError as e:
                    st.error("❌ Failed to fetch job openings from Zoho. Please try again later.")
                    logging.error(f"Zoho API error: {str(e)}")
                    return
                except Exception as e:
                    st.error("❌ An unexpected error occurred while fetching job openings.")
                    logging.exception("Unexpected error fetching job openings")
                    return

        job_options = {f"{job['title']}": job for job in st.session_state.active_jobs}

        job_container = st.container()
        st.markdown("""
            <style>
            .refresh-button-container {
                display: flex;
                align-items: flex-end;
                height: 100%;
                padding-bottom: 8px;
            }
            .refresh-button-container button {
                padding: 8px 12px !important;
                height: 38px !important;
                line-height: 1.2 !important;
                font-size: 14px !important;
                background-color: transparent !important;
                color: #fa4b4b !important;
                border: 1px solid #fa4b4b !important;
                border-radius: 6px !important;
                min-width: 45px !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
            }
            .refresh-button-container button:hover {
                color: white !important;
                background-color: #fa4b4b !important;
            }
            .stSelectbox > div > div {
                min-height: 38px;
            }
            </style>
        """, unsafe_allow_html=True)

        job_col, refresh_col = job_container.columns([10, 1])

        with job_col:
            selected_job_title = st.selectbox(
                label="Job Openings", label_visibility="collapsed",
                options=["Select Job Opening"] + list(job_options.keys()),
                index=0
            )

        with refresh_col:
            if st.button("🔄", key="refresh_jobs", help="Refresh job listings", use_container_width=True):
                st.session_state.active_jobs = None
                st.rerun()

        if selected_job_title and selected_job_title != "Select Job Opening":
            selected_job = job_options[selected_job_title]
            job_id = selected_job["id"]
            job_description = selected_job["description"]

            st.subheader("Job Description")
            st.markdown("""
                <style>
                .job-description {
                    background-color: #0e1117;
                    color: #ffffff;
                    padding: 0.5rem;
                    border-radius: 0.5rem;
                    border: 1px solid #e0e0e0;
                    max-height: 200px;
                    overflow-y: auto;
                    font-size: 13px;
                    line-height: 1.4;
                    margin: 8px 0;
                    white-space: pre-wrap;
                }
                </style>
            """, unsafe_allow_html=True)
            st.markdown(f'<div class="job-description">{job_description}</div>', unsafe_allow_html=True)

            sample_dir = None
            has_samples = False

            with st.expander("Sample Resume Configuration", expanded=False):
                sample_dir, has_samples = handle_sample_resumes(job_id, job_description)
                if has_samples:
                    st.info(
                        "✨ Sample resumes will be used to identify key characteristics "
                        "of successful candidates"
                    )

            # Check if we already have results for this job
            if st.session_state.zoho_results_df is not None:
                display_ranking_results(st.session_state.zoho_results_df, key_prefix=f"zoho_{job_id}")
                
            if st.button("Fetch and Rank Candidates", type="primary"):
                # Clear previous results and reset state when starting a new fetch
                st.session_state.zoho_results_df = None
                progress_bar = st.progress(0)
                progress_text = st.empty()

                try:
                    # Step 1: Fetch candidates
                    progress_bar.progress(10, text="🔍 Fetching candidates from Zoho...")
                    
                    # Get access token for API requests
                    access_token = get_access_token()
                    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
                    
                    # Fetch candidates using the job service
                    candidates = zoho_candidate_service.get_candidates_by_job_id(job_id, headers)

                    if not candidates:
                        progress_bar.progress(0, text="")
                        st.warning(
                            "## No Candidates Found\n\n"
                            "There are currently no candidates associated with this job opening in Zoho Recruit.\n\n"
                            "### Next Steps:\n"
                            "1. Check if you have candidates in Zoho Recruit\n"
                            "2. Ensure candidates are properly associated with this job opening\n"
                            "3. If you just added candidates, try refreshing the job listings"
                        )
                        return

                    # Step 2: Download resumes with progress tracking
                    progress_bar.progress(30, text=f"📥 Downloading {len(candidates)} resumes...")
                    
                    def update_progress(current, total):
                        progress = 30 + int(40 * (current / total)) if total > 0 else 30
                        progress_bar.progress(progress, text=f"📥 Downloaded {current} of {total} resumes...")
                    
                    # Download resumes in parallel with rate limiting
                    downloaded_files = zoho_candidate_service.batch_download_resumes(
                        candidates=candidates,
                        batch_size=50,  # Process 30 candidates per batch
                        delay=65  # 65 seconds between batches to respect rate limits
                    )
                    
                    if not downloaded_files:
                        progress_bar.progress(0, text="❌ No resumes were downloaded. Please check if candidates have attached resumes.")
                        return
                        
                    # Step 3: Initialize ranking service
                    progress_bar.progress(75, text="⚙️ Initializing ranking service...")
                    
                    ranker = RankingService(
                        model=model_choice,
                        scoring_weights=scoring_weights,
                        ranking_priority=priority_order
                    )

                    # Step 4: Process sample resumes if available
                    if has_samples and sample_dir and os.path.exists(sample_dir):
                        progress_bar.progress(80, text="🔍 Analyzing sample resumes...")
                        logging.info(f"Processing sample resumes from directory: {sample_dir}")
                        try:
                            ranker.analyze_example_resumes(sample_dir, job_description)
                            if ranker.llm_service.good_characteristics:
                                progress_bar.progress(85, text="✅ Successfully analyzed sample resumes")
                                logging.info("Successfully extracted characteristics from samples")
                            else:
                                progress_bar.progress(85, text="⚠️ Could not extract characteristics from samples")
                                logging.warning("No characteristics were extracted from samples")
                        except Exception as e:
                            logging.error(f"Error analyzing sample resumes: {str(e)}", exc_info=True)
                            progress_bar.progress(85, text="⚠️ Error analyzing sample resumes. Continuing without them.")
                    
                    # Step 5: Process all resumes
                    progress_bar.progress(90, text="📄 Processing candidate resumes...")
                    result = ranker.process_resumes(temp_dir, job_description)

                    # Step 6: Handle the result which could be an error or data
                    if 'error' in result:
                        if result.get('error_type') == 'INSUFFICIENT_QUOTA':
                            error_msg = "⚠️ OpenAI API quota exceeded. Please check your billing details and recharge your account."
                            progress_bar.progress(0, text=error_msg)
                            st.error(error_msg)
                            return
                        else:
                            error_msg = result.get('error', 'An unknown error occurred while processing resumes.')
                            progress_bar.progress(0, text=f"❌ {error_msg}")
                            st.error(error_msg)
                            return
                    
                    # If we have data, proceed with displaying results
                    results_df = result.get('data', pd.DataFrame())
                    
                    # Skip displaying results if we don't have any data
                    if results_df.empty:
                        progress_bar.progress(0, text="❌ No results were generated.")
                        st.error("No results were generated. Please check your input and try again.")
                        return
                        
                    # Store results in session state and display
                    progress_bar.progress(100, text="✅ Analysis complete!")
                    st.success("Analysis completed successfully!")
                    st.session_state.zoho_results_df = results_df
                    display_ranking_results(st.session_state.zoho_results_df, key_prefix=f"zoho_{job_id}")
                    
                    # Show failed downloads if any (separate from OpenAI quota errors)
                    failed_downloads = zoho_candidate_service.get_failed_downloads()
                    if failed_downloads:
                        st.subheader("⚠️ Candidates Without Resumes")
                        st.warning(f"Could not download resumes for {len(failed_downloads)} candidates. This usually happens when a candidate doesn't have a resume attached in Zoho.")
                        
                        # Create and display failed downloads table
                        failed_df = pd.DataFrame(failed_downloads)
                        failed_df = failed_df['name']  # Only show name 
                        failed_df.columns = ['Candidate Name']
                        
                        st.dataframe(
                            failed_df,
                            column_config={
                                'Candidate Name': st.column_config.TextColumn('Candidate Name')
                            },
                            hide_index=True,
                            use_container_width=True
                        )
                        
                        # Add download button for failed candidates
                        csv = failed_df.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label="📥 Download List of Candidates Without Resumes",
                            data=csv,
                            file_name="candidates_without_resumes.csv",
                            mime="text/csv"
                        )
                except Exception as e:
                    st.error(f"Error in Zoho integration: {str(e)}")
                    logging.error(f"Zoho integration error: {str(e)}")

                finally:
                    if progress_bar is not None:
                        progress_bar.empty()
                    if progress_text is not None:
                        progress_text.empty()

    except Exception as e:
        st.error(f"Error in Zoho integration: {str(e)}")
        logging.error(f"Zoho integration error: {str(e)}")

    finally:
        if zoho_candidate_service:
            zoho_candidate_service.cleanup_temp_dir()
        if temp_dir:
            CleanupService.cleanup_temp_files()

def handle_sample_resumes(job_id: str, job_description: str) -> tuple[str, bool]:
    """Handle fetching and processing of sample resumes from Zoho and user uploads."""
    has_samples = False
    sample_dir = ""
    
    use_sample_resumes = st.checkbox(
        "Use sample resumes (optional - improves ranking accuracy)",
        value=False,
        help="Enable to provide sample resumes that will be used to improve ranking accuracy"
    )
    
    if not use_sample_resumes:
        return "", False
        
    upload_method = st.radio(
        "Select resume source:",
        ["Zoho API", "Manual Upload"],
        horizontal=True
    )
    
    sample_dir = tempfile.mkdtemp()
    
    if upload_method == "Zoho API":
        sample_service = ZohoSampleProfileService()
        
        with st.spinner("Fetching and processing sample resumes from Zoho..."):
            zoho_sample_dir = sample_service.download_sample_profiles_by_job_id(job_id)
            
            if zoho_sample_dir and os.path.exists(zoho_sample_dir):
                try:
                    for filename in os.listdir(zoho_sample_dir):
                        src = os.path.join(zoho_sample_dir, filename)
                        dst = os.path.join(sample_dir, filename)
                        if os.path.isfile(src) and filename.lower().endswith(('.pdf', '.doc', '.docx')):
                            shutil.move(src, dst)
                    
                    files = [f for f in os.listdir(sample_dir) 
                            if os.path.isfile(os.path.join(sample_dir, f))]
                    
                    if files:
                        st.success(f"✅ Using {len(files)} sample resumes from Zoho")
                        has_samples = True
                        
                        import atexit
                        def cleanup_sample_dir():
                            if os.path.exists(sample_dir):
                                try:
                                    shutil.rmtree(sample_dir)
                                    logging.info(f"Cleaned up sample resumes directory: {sample_dir}")
                                except Exception as e:
                                    logging.error(f"Error cleaning up sample resumes directory: {str(e)}")
                        
                        atexit.register(cleanup_sample_dir)
                        return sample_dir, True
                    
                except Exception as e:
                    logging.error(f"Error processing Zoho resumes: {str(e)}")
                    st.error("Error processing resumes from Zoho. Please try Manual Upload mode.")
                    return "", False
                finally:
                    if zoho_sample_dir != sample_dir and os.path.exists(zoho_sample_dir):
                        try:
                            shutil.rmtree(zoho_sample_dir)
                        except:
                            pass
            
            st.info("No sample resumes found in Zoho for this job. Please switch to Manual Upload mode.")
            return "", False
    
    st.write("### Sample Resumes")
    st.write("Upload sample resumes to use for ranking (up to 5)")
    
    uploaded_samples = st.file_uploader(
        "Upload sample resumes",
        type=["pdf", "doc", "docx"],
        accept_multiple_files=True,
        key="manual_samples"
    )
    
    if uploaded_samples:
        if len(uploaded_samples) > 5:
            st.warning("Maximum 5 sample resumes allowed. Using first 5 files.")
            uploaded_samples = uploaded_samples[:5]
            
        if not sample_dir:
            sample_dir = tempfile.mkdtemp()
            
        for uploaded_file in uploaded_samples:
            file_path = os.path.join(sample_dir, uploaded_file.name)
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
        
        st.success(f"✅ Added {len(uploaded_samples)} sample resume(s)")
        has_samples = True
        
        import atexit
        def cleanup_sample_dir():
            if os.path.exists(sample_dir):
                try:
                    shutil.rmtree(sample_dir)
                    logging.info(f"Cleaned up sample resumes directory: {sample_dir}")
                except Exception as e:
                    logging.error(f"Error cleaning up sample resumes directory: {str(e)}")
        
        atexit.register(cleanup_sample_dir)
        return sample_dir, True
    
    if not has_samples and sample_dir and os.path.exists(sample_dir):
        try:
            shutil.rmtree(sample_dir)
            sample_dir = ""
        except Exception as e:
            logging.error(f"Error cleaning up temp directory: {str(e)}")
    
    return "", False

def main():
    st.title("Profile Ranking System")
    st.markdown(CSS_STYLES, unsafe_allow_html=True)
    
    # Initialize session states
    session_states = {
        'manual_results_df': None,
        'zoho_results_df': None,
        'active_jobs': None,
        'current_mode': None
    }
    
    for key, default in session_states.items():
        if key not in st.session_state:
            st.session_state[key] = default

    # Mode selection
    mode = st.radio(
        "Select Mode",
        ["Manual Ranking", "Sync from Zoho"],
        help="Choose between manual resume upload or Zoho Recruit integration",
        key="mode"
    )

    if mode != st.session_state.current_mode:
        if mode == "Manual Ranking":
            st.session_state.zoho_results_df = None
        else:
            st.session_state.manual_results_df = None
            if st.session_state.current_mode != "Sync from Zoho":
                st.session_state.active_jobs = None
        st.session_state.current_mode = mode

    def format_model_name(model_name):
        if model_name == "gpt-4o-mini":
            return f"{model_name} (May struggle with high resume volume.)"
        return model_name

    model_choice = st.selectbox(
        "Choose AI Model:",
        list(Settings.SUPPORTED_MODELS.keys()),
        index=0,
        format_func=format_model_name
    )

    if mode == "Manual Ranking":
        process_manual_mode(model_choice)
    else:
        process_zoho_mode(model_choice)

if __name__ == "__main__":
    try:
        main()
    finally:
        CleanupService.cleanup_temp_files()