import os
import time
import asyncio
from typing import Dict, List
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
import logging
from datetime import datetime
from ..config.prompt import PROMPT_TEMPLATE, PROMPT_TEMPLATE_GOOD, GOOD_RESUME_TEMPLATE
from ..utils.helpers import clean_llm_output
from dotenv import load_dotenv
from ..parsers.pypdf_parser import PyPDFParser
from ..parsers.docx_parser import DocxParser
from ..parsers.llama_parser import LlamaParser
from ..config.settings import Settings
from openai import RateLimitError, AuthenticationError
import streamlit as st
from tenacity import (
    retry,
    stop_after_attempt, 
    retry_if_exception_type,
    wait_random_exponential
)
import random

load_dotenv()
logging.basicConfig(level=logging.INFO)

class RateLimitHandler:
    def __init__(self, max_requests_per_minute=30, max_concurrent_requests=5):
        self.max_requests_per_minute = max_requests_per_minute
        self.max_concurrent_requests = max_concurrent_requests
        self.request_timestamps = []
        self.lock = asyncio.Lock()
        self.semaphore = asyncio.Semaphore(max_concurrent_requests)

    async def acquire(self):
        async with self.semaphore:  # Control concurrent requests
            async with self.lock:
                current_time = time.time()
                # Remove timestamps older than 1 minute
                self.request_timestamps = [ts for ts in self.request_timestamps if current_time - ts < 60]
                
                if len(self.request_timestamps) >= self.max_requests_per_minute:
                    # Calculate wait time until oldest request is 1 minute old
                    wait_time = 60 - (current_time - self.request_timestamps[0])
                    if wait_time > 0:
                        # Reduce wait time by 20% to be more aggressive
                        wait_time = wait_time * 0.8
                        await asyncio.sleep(wait_time)
                        return await self.acquire()
                
                self.request_timestamps.append(current_time)

class LLMService:
    def __init__(self, model: str):
        self.model = model
        # self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.openai_api_key = st.secrets ["OPENAI_API_KEY"]
        self.llm = self._initialize_llm()
        self.current_month_year = datetime.today().strftime("%B %Y")
        self.good_characteristics = []
        self.use_example_resumes = False
        self.current_job_description = None  # Add this line
        # Increase concurrent requests and requests per minute
        self.rate_limit_handler = RateLimitHandler(
            max_requests_per_minute=40,  # Increased from 25
            max_concurrent_requests=5    # Allow 5 concurrent requests
        )
        self.request_queue = asyncio.Queue()
        self.processing = False
        self.batch_size = 5  # Process resumes in batches of 5

    def _initialize_llm(self):
        """Initialize the OpenAI LLM."""
        try:
            if not self.openai_api_key:
                raise ValueError("OpenAI API key not found")
                
            provider = Settings.SUPPORTED_MODELS.get(self.model)
            if not provider:
                raise ValueError(f"Unsupported model: {self.model}")
                
            if provider == "openai":
                return ChatOpenAI(
                    model=self.model,
                    api_key=self.openai_api_key,
                    temperature=0.3,
                    top_p=1.0,
                    frequency_penalty=0.0,
                    presence_penalty=0.0,
                    n=1,
                    max_retries=3,
                    request_timeout=30, # Reduced timeout
                )

            
            raise ValueError(f"Unsupported provider: {provider}")
        except ValueError as e:
            raise ValueError(f"Error initializing LLM: {str(e)}")
        except Exception as e:
            raise Exception(f"Error initializing LLM: {str(e)}")

    def _generate_criteria_list(self, scoring_weights: Dict[str, float]) -> str:
        """Generate formatted criteria list for prompt."""
        return "\n".join(
            [f"- {k.capitalize()}: {v * 100}%"
             for k, v in scoring_weights.items()]
        )
    def _analyze_characteristics(self, resumes_text: str, analysis_type: str) -> list[str]:
        """Analyze resumes to extract characteristics"""
        try:
            if analysis_type != "good":
                logging.error("Invalid analysis type")
                return []
                
            
            # Create prompt template
            prompt = PromptTemplate(
                template=GOOD_RESUME_TEMPLATE,
                input_variables=["job_description", "resumes_text"]
            )
            
            # Create and run the chain
            chain = prompt | self.llm | StrOutputParser()
            response = chain.invoke({
                "job_description": self.current_job_description,
                "resumes_text": resumes_text
            })
            
            # Parse the response into a list of characteristics
            characteristics = []
            for line in response.split('\n'):
                line = line.strip()
                if line.startswith(('- ', '* ', '• ')):
                    characteristic = line[2:].strip()
                    if characteristic:
                        characteristics.append(characteristic)            
            return characteristics
            
        except Exception as e:
            logging.error(f"Error analyzing characteristics: {str(e)}")
            return []

    def analyze_example_resumes(self, good_resumes_dir: str = None, job_description: str = None):
        """Analyze example good resumes to extract characteristics"""
        logging.info("LLMService: Starting example resume analysis")
        
        # Reset state
        self.use_example_resumes = False
        self.good_characteristics = []
        self.current_job_description = job_description if job_description else "Not provided"
        
        if not good_resumes_dir:
            logging.warning("No good resumes directory provided, skipping analysis")
            return
            
        logging.info(f"Good resumes directory: {good_resumes_dir}")
        
        # Verify directory exists and is accessible
        if not os.path.exists(good_resumes_dir):
            logging.error(f"Good resumes directory does not exist: {good_resumes_dir}")
            return
            
        if not os.path.isdir(good_resumes_dir):
            logging.error(f"Path is not a directory: {good_resumes_dir}")
            return
            
        try:
            logging.info(f"Processing example resumes from: {good_resumes_dir}")
            good_text = self._read_resumes_from_dir(good_resumes_dir)
            
            if not good_text or not good_text.strip():
                logging.error("No content was extracted from any resume in the directory")
                return
                
            # Count number of resumes being analyzed
            resume_count = good_text.count("=== Resume:")
            if resume_count == 0:
                logging.warning("No resume sections found in the extracted content")
                return
                
            logging.info(f"Analyzing characteristics from {resume_count} good resumes")
            
            # Log a sample of the extracted text for debugging
            sample_text = good_text[:500].replace('\n', ' ')
            logging.debug(f"Sample extracted text (first 500 chars): {sample_text}...")
            
            # Extract characteristics from combined resumes
            self.good_characteristics = self._analyze_characteristics(good_text, "good")
            
            if not self.good_characteristics:
                logging.error("No characteristics could be extracted from the resumes")
                return
                
            self.use_example_resumes = True
            logging.info(f"Successfully extracted {len(self.good_characteristics)} characteristics")
            logging.info("=== Extracted Good Resume Characteristics ===")
            for i, char in enumerate(self.good_characteristics[:10], 1):
                logging.info(f"{i}. {char}")
            if len(self.good_characteristics) > 10:
                logging.info(f"... and {len(self.good_characteristics) - 10} more")
            logging.info("=" * 45)
            
        except Exception as e:
            logging.error(f"Error analyzing example resumes: {str(e)}", exc_info=True)
            self.use_example_resumes = False
            self.good_characteristics = []

    def _read_resumes_from_dir(self, directory: str) -> str:
        """Read and concatenate resumes from directory with a limit"""
        
        if not os.path.exists(directory):
            logging.warning(f"Directory not found: {directory}")
            return ""
        
        # Log directory contents for debugging
        try:
            dir_contents = os.listdir(directory)
            logging.info(f"Directory contents ({len(dir_contents)} items): {', '.join(dir_contents[:10])}" + 
                        ("..." if len(dir_contents) > 10 else ""))
        except Exception as e:
            logging.warning(f"Could not list directory contents: {str(e)}")
            
        resumes_text = []
        try:
            pdf_parser = PyPDFParser()
            docx_parser = DocxParser()
            llama_parser = LlamaParser()  # Initialize LlamaParse
            
            # Get all files and sort them
            files = [f for f in os.listdir(directory) 
                    if f.lower().endswith(('.pdf', '.doc', '.docx'))]
            files.sort()
            
            if not files:
                logging.warning(f"No supported files found in directory: {directory}")
                return ""
                
            logging.info(f"Found {len(files)} supported files in directory")
            
            for filename in files:
                file_path = os.path.join(directory, filename)
                content = None
                
                # Check if file exists and has content
                if not os.path.exists(file_path):
                    logging.error(f"File not found: {file_path}")
                    continue
                    
                if os.path.getsize(file_path) == 0:
                    logging.warning(f"Empty file: {filename}")
                    continue
                
                try:
                    logging.info(f"Processing file: {filename} (Size: {os.path.getsize(file_path)} bytes)")
                    
                    if filename.lower().endswith('.pdf'):
                        # Try PyPDF first
                        logging.debug(f"Trying PyPDF parser for {filename}")
                        content = pdf_parser.parse(file_path)
                        
                        # If PyPDF fails or returns empty content, try LlamaParse
                        if not content or not content.get("content") or not content.get("content").strip():
                            logging.info(f"PyPDF parser failed for {filename}, trying LlamaParse")
                            content = llama_parser.parse(file_path)
                            
                    elif filename.lower().endswith('.docx'):
                        # Try docx parser first for .docx files
                        logging.debug(f"Trying DOCX parser for {filename}")
                        content = docx_parser.parse(file_path)
                        
                        # If docx parser fails, try LlamaParse
                        if not content or not content.get("content") or not content.get("content").strip():
                            logging.info(f"DOCX parser failed for {filename}, trying LlamaParse")
                            content = llama_parser.parse(file_path)
                            
                    elif filename.lower().endswith('.doc'):
                        # Use LlamaParse directly for .doc files
                        logging.debug(f"Using LlamaParse for .doc file: {filename}")
                        content = llama_parser.parse(file_path)
                    
                    # Add successfully parsed content
                    if content and content.get("content") and content.get("content").strip():
                        resumes_text.append(f"=== Resume: {filename} ===\n{content['content']}\n")
                        logging.info(f"Successfully extracted content from {filename} using {content.get('parser_used', 'unknown parser')}")
                        
                        # Log first 200 chars for debugging
                        sample = content['content'][:200].replace('\n', ' ')
                        logging.debug(f"Sample content from {filename}: {sample}...")
                    else:
                        logging.warning(f"Failed to extract content from {filename} with all parsers")
                        # Try to read file as text as a last resort
                        try:
                            with open(file_path, 'rb') as f:
                                raw_content = f.read().decode('utf-8', errors='ignore')
                                if raw_content.strip():
                                    logging.info(f"Adding raw content from {filename} (fallback)")
                                    resumes_text.append(f"=== Resume (raw): {filename} ===\n{raw_content}\n")
                        except Exception as e:
                            logging.error(f"Failed to read file {filename} as raw text: {str(e)}")
                        
                except Exception as e:
                    logging.error(f"Error processing {filename}: {str(e)}", exc_info=True)
                    
            # Combine all resume texts
            combined_text = "\n\n".join(resumes_text)
            logging.info(f"Successfully processed {len(resumes_text)}/{len(files)} resumes")
            
            if not combined_text.strip():
                logging.warning("No content was extracted from any resume")
            
            return combined_text
                
        except Exception as e:
            logging.error(f"Error reading directory {directory}: {str(e)}", exc_info=True)
            return ""

    @retry(
        retry=retry_if_exception_type((RateLimitError, Exception)),
        wait=wait_random_exponential(min=0.5, max=30),  # Reduced wait times
        stop=stop_after_attempt(5)
    )
    async def _analyze_resume_with_retry(self, input_vars: dict, template: str) -> Dict:
        """Execute single resume analysis with enhanced retry logic"""
        start_time = time.time()
        try:
            # Wait for rate limit
            await self.rate_limit_handler.acquire()
            # Create prompt template
            prompt = PromptTemplate(
                template=template,
                input_variables=list(input_vars.keys())
            )
            
            # Create chain and execute
            chain = prompt | self.llm | StrOutputParser()
            result = await chain.ainvoke(input_vars)
            parsed_result = clean_llm_output(result)
            
            # Add processing time to the result
            processing_time = time.time() - start_time
            parsed_result["processing_time"] = round(processing_time, 2)
            return parsed_result
            
        except RateLimitError as e:
            error_message = str(e).lower()
            if 'insufficient_quota' in error_message or 'quota' in error_message:
                logging.error("Insufficient quota error from OpenAI API")
                error_response = self._generate_error_response(error_type="INSUFFICIENT_QUOTA")
                error_response["processing_time"] = round(time.time() - start_time, 2)
                return error_response
                
            logging.warning(f"Rate limit hit, waiting before retry: {str(e)}")
            # Reduced jitter range
            await asyncio.sleep(random.uniform(0.5, 2))
            raise
        except AuthenticationError as e:
            logging.error(f"Authentication error with OpenAI API: {str(e)}")
            error_response = self._generate_error_response(error_type="AUTH_ERROR")
            error_response["processing_time"] = round(time.time() - start_time, 2)
            return error_response
        except Exception as e:
            logging.error(f"Error in resume analysis: {str(e)}")
            error_response = self._generate_error_response()
            error_response["processing_time"] = round(time.time() - start_time, 2)
            return error_response

    async def _process_queue(self):
        """Process items from the request queue with batch processing"""
        while True:
            try:
                if self.request_queue.empty():
                    self.processing = False
                    break
                
                # Process in batches
                batch = []
                for _ in range(self.batch_size):
                    if self.request_queue.empty():
                        break
                    batch.append(await self.request_queue.get())
                
                if not batch:
                    continue
                
                # Process batch concurrently
                tasks = []
                for input_vars, template, future in batch:
                    task = asyncio.create_task(self._process_single_item(input_vars, template, future))
                    tasks.append(task)
                
                await asyncio.gather(*tasks)
                
            except Exception as e:
                logging.error(f"Error processing queue: {str(e)}")
                await asyncio.sleep(0.5)  # Reduced sleep time

    async def _process_single_item(self, input_vars, template, future):
        """Process a single queue item"""
        try:
            result = await self._analyze_resume_with_retry(input_vars, template)
            future.set_result(result)
        except Exception as e:
            future.set_exception(e)
        finally:
            self.request_queue.task_done()

    async def _analyze_resumes_batch(self, resume_batches: List[Dict], template: str) -> List[Dict]:
        """Process multiple resumes with improved parallelization"""
        results = []
        futures = []
        
        # Create futures for each resume
        for batch in resume_batches:
            future = asyncio.Future()
            futures.append(future)
            await self.request_queue.put((batch, template, future))
        
        # Start processing if not already running
        if not self.processing:
            self.processing = True
            asyncio.create_task(self._process_queue())
        
        # Wait for all futures to complete
        try:
            results = await asyncio.gather(*futures, return_exceptions=True)
            # Filter out exceptions and replace with error responses
            results = [
                result if not isinstance(result, Exception) else self._generate_error_response()
                for result in results
            ]
        except Exception as e:
            logging.error(f"Error in batch processing: {str(e)}")
            results = [self._generate_error_response() for _ in resume_batches]
        
        return results

    def analyze_resume(self, resume_text: str, job_description: str, 
                      scoring_weights: Dict[str, float], priority_order: str) -> Dict:
        """Analyze single resume with rate limit handling"""
        try:
            # Prepare input variables
            if self.use_example_resumes and self.good_characteristics:
                template = PROMPT_TEMPLATE_GOOD
                input_vars = {
                    "current_month_year": self.current_month_year,
                    "criteria_list": self._generate_criteria_list(scoring_weights),
                    "priority_order": priority_order,
                    "job_desc": job_description,
                    "resume": resume_text,
                    "good_resume_characteristics": "\n".join(f"- {c}" for c in self.good_characteristics)
                }
            else:
                template = PROMPT_TEMPLATE
                input_vars = {
                    "current_month_year": self.current_month_year,
                    "criteria_list": self._generate_criteria_list(scoring_weights),
                    "priority_order": priority_order,
                    "job_desc": job_description,
                    "resume": resume_text
                }

            # Run async analysis
            result = asyncio.run(self._analyze_resume_with_retry(input_vars, template))
            return result

        except Exception as e:
            logging.error(f"Error in analyze_resume: {str(e)}")
            return self._generate_error_response()



    async def analyze_resumes_batch_async(
        self, 
        resume_texts: List[str],
        job_description: str,
        scoring_weights: Dict[str, float],
        priority_order: str,
        file_names: List[str]
    ) -> List[Dict]:
        """Async version of analyze_resumes_batch"""
        try:
            # Log which template is being used
            template_type = "GOOD_RESUME_TEMPLATE" if self.use_example_resumes and self.good_characteristics else "STANDARD_TEMPLATE"
            logging.info(f"Using {template_type} for resume analysis")
            if template_type == "GOOD_RESUME_TEMPLATE":
                logging.info(f"Number of good characteristics being used: {len(self.good_characteristics)}")
            
            # Prepare input variables for each resume
            resume_batches = []
            for resume_text, file_name in zip(resume_texts, file_names):
                if self.use_example_resumes and self.good_characteristics:
                    template = PROMPT_TEMPLATE_GOOD
                    input_vars = {
                        "current_month_year": self.current_month_year,
                        "criteria_list": self._generate_criteria_list(scoring_weights),
                        "priority_order": priority_order,
                        "job_desc": job_description,
                        "resume": resume_text,
                        "good_resume_characteristics": "\n".join(f"- {c}" for c in self.good_characteristics),
                        "file_name": file_name
                    }
                else:
                    template = PROMPT_TEMPLATE
                    input_vars = {
                        "current_month_year": self.current_month_year,
                        "criteria_list": self._generate_criteria_list(scoring_weights),
                        "priority_order": priority_order,
                        "job_desc": job_description,
                        "resume": resume_text,
                        "file_name": file_name
                    }
                resume_batches.append(input_vars)

            # Process all resumes in batches
            results = await self._analyze_resumes_batch(resume_batches, template)
            
            # Add file name to results
            for idx, result in enumerate(results):
                if isinstance(result, dict) and "information" in result:
                    result["information"]["File"] = resume_batches[idx]["file_name"]
                
            return results

        except Exception as e:
            logging.error(f"Error in analyze_resumes_batch_async: {str(e)}")
            return [self._generate_error_response() for _ in resume_texts]

    def _generate_error_response(self, error_type="GENERIC"):
        """Generate a standardized error response
        
        Args:
            error_type: Type of error (GENERIC, INSUFFICIENT_QUOTA, AUTH_ERROR)
        """
        if error_type == "INSUFFICIENT_QUOTA":
            explanation = "OpenAI API quota exceeded. Please check your billing details and recharge your account."
        elif error_type == "AUTH_ERROR":
            explanation = "Authentication error with OpenAI API. Please check your API key."
        else:
            explanation = "Error analyzing resume"
            
        return {
            "information": {
                "error_type": error_type
            },
            "evaluation": {
                "total_score": 0,
                "explanation": explanation
            },
            "processing_time": 0,
            "error": True,
            "error_type": error_type
        }