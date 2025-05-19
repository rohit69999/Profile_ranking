import streamlit as st
from app.services.ranking_service import RankingService
import pandas as pd
from app.parsers.docx_parser import DocxParser
from app.parsers.pypdf_parser import PyPDFParser
from app.services.cleanup_service import CleanupService
from app.config.settings import Settings
import tempfile
import os
import shutil 
import logging

def save_uploaded_files(uploaded_files):
    """Save uploaded files to a temporary directory and return the directory path."""
    temp_dir = tempfile.mkdtemp()
    
    for uploaded_file in uploaded_files:
        file_path = os.path.join(temp_dir, uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
    
    return temp_dir

def main():
    if 'results_df' not in st.session_state:
        st.session_state.results_df = None

    st.title("Profile Ranking System")
    st.write("Upload resumes and job description to rank candidates.")
    
    model_choice = st.selectbox(
        "Choose AI Model:",
        list(Settings.SUPPORTED_MODELS.keys()),
        index=0
    )

    # Job description input
    job_desc_file = st.file_uploader(
        "Upload Job Description", 
        type=["txt", "doc", "docx", "pdf"]
    )

    # Resume uploads section
    # st.subheader("Upload Resumes")
    uploaded_files = st.file_uploader(
        "Upload resumes to evaluate (PDF, DOC, DOCX)",
        type=["pdf", "doc", "docx"],
        accept_multiple_files=True,
        key="resumes"
    )
    
    # Sample good resumes section
    good_resumes = st.file_uploader(
        "Upload sample good resumes",
        type=["pdf", "doc", "docx"],
        accept_multiple_files=True,
        key="good_resumes"
    )

    # Sidebar configuration
    st.sidebar.header("Scoring Configuration")
    st.sidebar.write("Adjust the weights for each scoring criterion (must sum to 100%).")
    
    skills_weight = st.sidebar.slider("Skills Match Weight (%)", 0, 100, 35)
    total_professional_experience_weight = st.sidebar.slider("Total Professional Experience Weight (%)", 0, 100, 15)
    total_relevant_experience_weight = st.sidebar.slider("Relevant Experience Weight (%)", 0, 100, 15)
    education_weight = st.sidebar.slider("Education Weight (%)", 0, 100, 15)
    certifications_weight = st.sidebar.slider("Certifications Weight (%)", 0, 100, 10)
    location_weight = st.sidebar.slider("Location Weight (%)", 0, 100, 10)
    
    total_weight = (skills_weight + total_professional_experience_weight + 
                   total_relevant_experience_weight + education_weight + 
                   certifications_weight + location_weight)
    if total_weight != 100:
        st.sidebar.error("Weights must sum to 100%. Please adjust the values.")
    
    st.sidebar.header("Tie-Breaking Priority")
    st.sidebar.write("Set the priority order for breaking ties between candidates with the same score.")
    
    priority_order = st.sidebar.multiselect(
        "Priority Order (drag to reorder):",
        options=["skills_match", "total_professional_experience", "total_relevant_experience", 
                "education", "certifications", "location"],
        default=["skills_match", "total_relevant_experience", "total_professional_experience", 
                "education", "certifications", "location"]
    )
    
    # Create three columns for button centering
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        # Custom CSS for the button
        st.markdown("""
            <style>
            div.stButton > button {
                background-color: #fa4b4b;
                color: white;
                font-size: 16px;
                padding: 10px 16px;
                width: auto;
                margin: 0 auto;         /* This centers the button horizontally */
                display: block;         /* Required to make margin auto work */
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
            
            if total_weight != 100:
                st.warning("Scoring weights must sum to 100%. Please adjust the weights.")
                return

            # Add function to read job description file
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
                        
                    # Create temporary directory and file
                    temp_dir = tempfile.mkdtemp()
                    temp_path = os.path.join(temp_dir, f"job_desc_temp.{file_extension}")
                    
                    # Save uploaded file content
                    with open(temp_path, "wb") as f:
                        f.write(uploaded_file.getvalue())
                        f.flush()
                        os.fsync(f.fileno())

                    # Select appropriate parser
                    if file_extension in ["doc", "docx"]:
                        parser = DocxParser()
                    elif file_extension == "pdf":
                        parser = PyPDFParser()
                    else:
                        raise ValueError(f"Unsupported file extension: {file_extension}")
                
                    # Parse the file
                    result = parser.parse(temp_path)
                    
                    if not result or not result.get("content"):
                        raise ValueError("Parser returned no content")
                        
                    return result["content"]
                        
                except Exception as e:
                    logging.error(f"Error reading file {uploaded_file.name}: {str(e)}")
                    st.error(f"Error reading job description file: {str(e)}")
                    return ""
                
                finally:
                    # Use cleanup service
                    CleanupService.cleanup_job_desc_files(temp_path, temp_dir)

            # Extract job description text if file is uploaded
            job_description = ""
            if job_desc_file:
                with st.spinner("Reading job description..."):
                    job_description = read_job_description(job_desc_file)
                    if not job_description:
                        st.error("Failed to read job description file. Please check the file and try again.")

            try:
                with st.spinner("Processing resumes..."):
                    # Save uploaded files
                    temp_dir = save_uploaded_files(uploaded_files)
                    
                    # Process good resumes first if provided
                    if good_resumes:
                        num_resumes = len(good_resumes)
                        if num_resumes > 5:
                            st.warning(f"Note: Only the first 5 sample resumes will be processed (you uploaded {num_resumes})")
                        good_dir = save_uploaded_files(good_resumes)
                    else:
                        good_dir = None
                        
                    # Convert scoring weights
                    scoring_weights = {
                        "skills_match": float(skills_weight) / 100,
                        "total_professional_experience": float(total_professional_experience_weight) / 100,
                        "total_relevant_experience": float(total_relevant_experience_weight) / 100,
                        "education": float(education_weight) / 100,
                        "certifications": float(certifications_weight) / 100,
                        "location": float(location_weight) / 100
                    }
                    
                    # Initialize ranker
                    ranker = RankingService(
                        model=model_choice,
                        scoring_weights=scoring_weights,
                        ranking_priority=priority_order
                    )
                    
                    # Set example directory if good resumes were provided
                    if good_dir:
                        ranker.example_good_dir = good_dir
                    
                    # Process all resumes
                    results_df = ranker.process_resumes(temp_dir, job_description)
                    
                    if not results_df.empty:
                        st.session_state.results_df = results_df
                    else:
                        st.error("No results were generated. Please check the uploaded files and try again.")
                    
                    # Use cleanup service instead of direct cleanup
                    CleanupService.cleanup_upload_dirs(temp_dir, good_dir)
                        
            except Exception as e:
                st.error(f"An error occurred: {str(e)}")

    # Move results display outside the button click handler
    if st.session_state.results_df is not None:
        results_df = st.session_state.results_df
        st.subheader("Rankings:")
        
        # Add filter controls
        col1, col2 = st.columns(2)
        with col1:
            show_top_n = st.number_input(
                "Show Top N Candidates", 
                min_value=1, 
                max_value=len(results_df),
                value=len(results_df),
                help="Filter number of candidates to display"
            )
        with col2:
            min_score = st.slider(
                "Minimum Score Filter",
                min_value=float(50),
                max_value=float(100),
                value=float(results_df['total_score'].min()),
                step=10.0,
                help="Filter candidates by minimum score"
            )

        # Apply filters to create display DataFrame
        display_df = results_df.copy()
        
        # Apply score filter
        display_df = display_df[display_df['total_score'] >= min_score]
        
        # Apply top N filter
        if len(display_df) > show_top_n:
            display_df = display_df.head(show_top_n)
        
        # Show filter summary
        st.info(f"Showing {len(display_df)} candidates out of {len(results_df)} total matches (Score ≥ {min_score:.2f})")
        # Format numeric columns
        display_df['total_score'] = display_df['total_score'].apply(lambda x: f"{x:.2f}")
        display_df['total_professional_experience'] = display_df['total_professional_experience'].apply(lambda x: f"{x:.1f}")
        display_df['total_relevant_experience'] = display_df['total_relevant_experience'].apply(lambda x: f"{x:.1f}")
        display_df['processing_time'] = display_df['processing_time'].apply(lambda x: f"{x:.2f}s")

        # Set column configuration
        column_config = {
            "Rank": st.column_config.NumberColumn(
                "Rank",
                help="Candidate ranking based on total score",
                format="%d"
            ),
            "name": st.column_config.TextColumn(
                "Name",
                help="Candidate name"
            ),
            "total_score": st.column_config.NumberColumn(
                "Score",
                help="Total evaluation score",
                format="%.2f"
            ),
            "total_professional_experience": st.column_config.NumberColumn(
                "Total Professional Experience (Years)",
                help="Total years of professional experience (excluding internships)",
                format="%.1f"
            ),
            "total_relevant_experience": st.column_config.NumberColumn(
                "Relevant Experience (Years)",
                help="Years of experience relevant to the job description",
                format="%.1f"
            ),
            "skills": st.column_config.TextColumn(
                "Skills",
                help="Relevant skills identified"
            ),
            "email": st.column_config.TextColumn(
                "Email",
                help="Contact email"
            ),
            "phone": st.column_config.TextColumn(
                "Phone",
                help="Contact phone number"
            ),
            "location_info": st.column_config.TextColumn(
                "Location",
                help="Candidate location"
            ),
            "File": st.column_config.TextColumn(
                "Resume File",
                help="Source resume file"
            ),
            "processing_time": st.column_config.NumberColumn(
                "Processing Time (s)",
                help="Time taken to process the resume",
                format="%.2f"
            )
        }
        
        # Display the formatted DataFrame
        st.dataframe(
            display_df,
            column_config=column_config,
            hide_index=True,
            use_container_width=True
        )
        
        # Add custom CSS for download buttons
        st.markdown("""
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
        """, unsafe_allow_html=True)

        # Add download buttons
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

if __name__ == "__main__":
    try:
        main()
    finally:
        # Ensure cleanup runs when the app shuts down
        CleanupService.cleanup_temp_files()
