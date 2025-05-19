from typing import List, Dict
import pandas as pd
import logging
from ..parsers.pypdf_parser import PyPDFParser
from ..parsers.llama_parser import LlamaParser
from ..parsers.docx_parser import DocxParser
from .llm_service import LLMService
from ..config.settings import Settings
import time
import os
import glob
import concurrent.futures
logging.basicConfig(level=logging.INFO)


class RankingService:
    def __init__(self, model: str,
                 scoring_weights: Dict[str, float] = None,
                 ranking_priority: List[str] = None):
        self.llm_service = LLMService(model)
        self.scoring_weights = scoring_weights or Settings.DEFAULT_WEIGHTS
        self.ranking_priority = ranking_priority or Settings.DEFAULT_PRIORITY
        self.example_good_dir = None
        self._initialize_parsers()

    def _initialize_parsers(self):
        self.pdf_parser = PyPDFParser()
        self.docx_parser = DocxParser()
        self.llama_parser = LlamaParser()

    def process_resumes(self, resume_dir: str, job_description: str) -> pd.DataFrame:
        overall_start_time = time.time()
        
        if not os.path.exists(resume_dir):
            logging.error(f"Resume directory not found: {resume_dir}")
            return pd.DataFrame()
            
        try:
            # First, analyze good resumes if provided
            if self.example_good_dir:
                logging.info("Processing sample good resumes first...")
                self.llm_service.analyze_example_resumes(
                    good_resumes_dir=self.example_good_dir,
                    job_description=job_description
                )
                logging.info("Completed analyzing good resumes")
            
            # Process candidate resumes
            file_patterns = [
                os.path.join(resume_dir, "*.pdf"),
                os.path.join(resume_dir, "*.docx"),
                os.path.join(resume_dir, "*.doc")
            ]

            all_files = []
            for pattern in file_patterns:
                all_files.extend(glob.glob(pattern))

            if not all_files:
                logging.warning("No resumes found in the specified directory")
                return pd.DataFrame()

            results = []
            # Use ThreadPoolExecutor for parallel processing
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                # Submit all resume processing tasks
                future_to_file = {
                    executor.submit(self._process_single_resume, file_path, job_description, overall_start_time): file_path
                    for file_path in all_files
                }
                for future in concurrent.futures.as_completed(future_to_file):
                    file_path = future_to_file[future]
                    try:
                        result = future.result()
                        if result:
                            results.append(result)
                    except Exception as e:
                        logging.error(f"Error processing {file_path}: {str(e)}")
                        continue

            # Create and return results DataFrame
            return self._create_results_dataframe(results)
            
        except Exception as e:
            logging.error(f"Error in process_resumes: {str(e)}")
            return pd.DataFrame()

    def _process_single_resume(self, file_path: str, job_description: str, overall_start_time: float):
        logging.info(f"Processing resume: {file_path}")
        
        # Parse content
        content = None
        if file_path.lower().endswith('.pdf'):
            try:
                # Always use hybrid mode
                try:
                    content = self.pdf_parser.parse(file_path)
                    if not content or not content.get("content") or not content.get("content").strip():
                        logging.warning(f"PyPDF parser failed for {file_path}, trying LlamaParse")
                        content = self.llama_parser.parse(file_path)
                except Exception as pdf_error:
                    logging.error(f"PyPDF parser error: {str(pdf_error)}, falling back to LlamaParse")
                    content = self.llama_parser.parse(file_path)
            except Exception as parse_error:
                logging.error(f"Error parsing {file_path}: {str(parse_error)}")
                return None
        else:
            try:
                content = self.docx_parser.parse(file_path)
            except Exception as docx_error:
                logging.error(f"Error parsing {file_path}: {str(docx_error)}")
                return None

        if not content or not content.get("content"):
            logging.error(f"Failed to extract content from {file_path}")
            return None

        # Analyze resume
        analysis = self.llm_service.analyze_resume(
            content["content"],
            job_description,
            self.scoring_weights,
            self.ranking_priority
        )

        if analysis and isinstance(analysis, dict) and 'information' in analysis and 'evaluation' in analysis:
            info = analysis["information"]
            scores = analysis["evaluation"]
            
            result = {
                'name': info.get('name', 'Not found'),
                'total_score': scores.get('total_score', 0),
                'skills': ", ".join(info.get('skills', [])),
                'total_professional_experience': info.get('total_professional_experience', 0),
                'total_relevant_experience': info.get('total_relevant_experience', 0),
                'phone': info.get('phone', 'Not found'),
                'email': info.get('email', 'add'),
                'location_info': info.get('location', 'Not found'),
                'File': os.path.basename(file_path),
                'processing_time': round(time.time() - overall_start_time, 2)
            }
            logging.info(f"Successfully processed resume for: {info.get('name', 'unnamed candidate')}")
            return result
        else:
            logging.error(f"Invalid or incomplete analysis result for {file_path}")
            logging.debug(f"Analysis result: {analysis}")
            return None

    def _create_results_dataframe(self, results: List[Dict]):
        """Create a DataFrame from the results list."""
        if not results:
            return pd.DataFrame(columns=[
                'Rank', 'name', 'total_score', 'total_professional_experience',
                'total_relevant_experience', 'skills', 'email', 'phone', 'location_info', 'File', 'processing_time'
            ])

        df = pd.DataFrame(results)
        
        # Ensure numeric columns are properly formatted
        df['total_score'] = pd.to_numeric(df['total_score'], errors='coerce').round(2)
        df['total_professional_experience'] = pd.to_numeric(df.get('total_professional_experience', 0), errors='coerce').round(1)
        df['total_relevant_experience'] = pd.to_numeric(df.get('total_relevant_experience', 0), errors='coerce').round(1)
        df['processing_time'] = pd.to_numeric(df['processing_time'], errors='coerce').round(2)
        
        # Sort by total score and reset index for ranking
        df = df.sort_values('total_score', ascending=False).reset_index(drop=True)
        df.insert(0, 'Rank', range(1, len(df) + 1))
        
        # Format columns for display
        df['skills'] = df['skills'].fillna('')
        df['name'] = df['name'].fillna('Not found')
        df['email'] = df['email'].fillna('Not found')
        df['phone'] = df['phone'].fillna('Not found')
        df['location_info'] = df['location_info'].fillna('Not found')
        
        # Reorder columns for better presentation
        columns = [
            'Rank',
            'name',
            'total_score',
            'total_professional_experience',
            'total_relevant_experience',
            'skills',
            'email',
            'phone',
            'location_info',
            'File',
            'processing_time'
        ]
        
        return df[columns]

    def analyze_example_resumes(self, good_resumes_dir: str = None, bad_resumes_dir: str = None):
        """Analyze example resumes to extract characteristics"""
        try:
            if good_resumes_dir and not os.path.exists(good_resumes_dir):
                logging.warning(f"Good resumes directory not found: {good_resumes_dir}")
                return
                
            if bad_resumes_dir and not os.path.exists(bad_resumes_dir):
                logging.warning(f"Bad resumes directory not found: {bad_resumes_dir}")
                return
                
            self.llm_service.analyze_example_resumes(good_resumes_dir, bad_resumes_dir)
        except Exception as e:
            logging.error(f"Error analyzing example resumes: {str(e)}")