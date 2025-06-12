from typing import List, Dict
import pandas as pd
import logging
import nest_asyncio
from ..parsers.pypdf_parser import PyPDFParser
from ..parsers.llama_parser import LlamaParser
from ..parsers.docx_parser import DocxParser
from .llm_service import LLMService
from ..config.settings import Settings
import os
import glob
import asyncio

# Apply nest_asyncio at the start
nest_asyncio.apply()


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

    async def _parse_file_async(self, file_path: str) -> tuple[str, str]:
        """Parse a single file asynchronously"""
        try:
            content = None
            file_name = os.path.basename(file_path)
            
            if file_path.lower().endswith('.pdf'):
                content = self.pdf_parser.parse(file_path)
                if not content or not content.get("content", "").strip():
                    content = await self.llama_parser.aparse(file_path)
            else:
                content = self.docx_parser.parse(file_path)

            if content and content.get("content"):
                return file_name, content["content"]
            
            logging.error(f"Failed to extract content from {file_path}")
            return None, None

        except Exception as e:
            logging.error(f"Error processing {file_path}: {str(e)}")
            return None, None

    async def _parse_files_parallel(self, all_files: List[str]) -> tuple[List[str], List[str]]:
        """Parse multiple files in parallel with proper async handling"""
        resume_texts = []
        file_names = []
        
        # Create semaphore to limit concurrent file parsing
        semaphore = asyncio.Semaphore(2)  # Reduce concurrent operations further
        
        async def parse_with_semaphore(file_path: str):
            async with semaphore:
                try:
                    result = await self._parse_file_async(file_path)
                    # Increased delay between operations to avoid rate limits
                    await asyncio.sleep(0.5)
                    return result
                except Exception as e:
                    logging.error(f"Error processing file {file_path}: {str(e)}")
                    return None, None
    
        # Process files in smaller batches
        batch_size = 3
        for i in range(0, len(all_files), batch_size):
            batch = all_files[i:i + batch_size]
            
            # Create tasks for current batch
            tasks = [parse_with_semaphore(file_path) for file_path in batch]
            
            # Execute batch with proper error handling
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process batch results
            for result in batch_results:
                if isinstance(result, tuple) and result[0] and result[1]:
                    file_name, content = result
                    file_names.append(file_name)
                    resume_texts.append(content)
                elif isinstance(result, Exception):
                    logging.error(f"Error in parallel processing: {str(result)}")
            
            # Add delay between batches
            await asyncio.sleep(1.0)

        return resume_texts, file_names

    async def process_resumes_async(self, resume_dir: str, job_description: str) -> pd.DataFrame:
        """Async version of process_resumes"""
        try:
            if not os.path.exists(resume_dir):
                logging.error(f"Resume directory not found: {resume_dir}")
                return pd.DataFrame()
                
            # Get all files
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

            # Parse files in parallel
            resume_texts, file_names = await self._parse_files_parallel(all_files)

            if not resume_texts:
                logging.warning("No valid content extracted from any resume")
                return pd.DataFrame()

            # Process resumes with rate limiting
            results = await self.llm_service.analyze_resumes_batch_async(
                resume_texts,
                job_description,
                self.scoring_weights,
                self.ranking_priority,
                file_names
            )

            return self._create_results_dataframe(results)
            
        except Exception as e:
            logging.error(f"Error in process_resumes_async: {str(e)}")
            return pd.DataFrame()
            
    def process_resumes(self, resume_dir: str, job_description: str) -> pd.DataFrame:
        """Synchronous wrapper for process_resumes_async"""
        return asyncio.run(self.process_resumes_async(resume_dir, job_description))

    def _create_results_dataframe(self, results: List[Dict]):
        """Create a DataFrame from the results list."""
        if not results:
            return pd.DataFrame(columns=[
                'Rank', 'name', 'total_score', 'total_professional_experience',
                'total_relevant_experience', 'skills', 'email', 'phone', 
                'location_info', 'File', 'processing_time'
            ])

        # Process each result to ensure required fields exist
        processed_results = []
        for analysis in results:
            try:
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
                        'email': info.get('email', 'Not found'),
                        'location_info': info.get('location', 'Not found'),
                        'File': info.get('File', 'Unknown'),  # Ensure file name is included
                        'processing_time': analysis.get('processing_time', 0)  # Ensure processing time is included
                    }
                    processed_results.append(result)
                else:
                    logging.error(f"Invalid or incomplete analysis result")
                    continue
            except Exception as e:
                logging.error(f"Error processing result: {str(e)}")
                continue

        # Create DataFrame with processed results
        df = pd.DataFrame(processed_results)
        
        # Ensure numeric columns are properly formatted
        df['total_score'] = pd.to_numeric(df['total_score'], errors='coerce').fillna(0).round(2)
        df['total_professional_experience'] = pd.to_numeric(df['total_professional_experience'], errors='coerce').fillna(0).round(1)
        df['total_relevant_experience'] = pd.to_numeric(df['total_relevant_experience'], errors='coerce').fillna(0).round(1)
        df['processing_time'] = pd.to_numeric(df['processing_time'], errors='coerce').fillna(0).round(2)
        
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

    def analyze_example_resumes(self, good_resumes_dir: str = None, job_description: str = None):
        """Analyze example good resumes to extract characteristics"""
        try:
            if not good_resumes_dir:
                logging.info("No good resumes directory provided; skipping good resume analysis.")
                return
            
            if not os.path.exists(good_resumes_dir):
                logging.warning(f"Good resumes directory not found: {good_resumes_dir}")
                return

            logging.info("Starting good resume characteristics analysis...")
            self.example_good_dir = good_resumes_dir
            
            self.llm_service.analyze_example_resumes(good_resumes_dir, job_description)
            
            if self.llm_service.good_characteristics:
                logging.info(f"Extracted {len(self.llm_service.good_characteristics)} characteristics from good resumes")
                logging.info("Good resume feature is " + 
                            ("ENABLED" if self.llm_service.use_example_resumes else "DISABLED"))
            else:
                logging.warning("No characteristics were extracted from good resumes")

        except Exception as e:
            logging.error(f"Error analyzing example resumes: {str(e)}")