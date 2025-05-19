import os
import time
from typing import Dict
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
import json
import re
import logging
from datetime import datetime
from ..config.prompt import PROMPT_TEMPLATE, PROMPT_TEMPLATE_GOOD, GOOD_RESUME_TEMPLATE
from ..utils.helpers import clean_llm_output
from dotenv import load_dotenv
from ..parsers.pypdf_parser import PyPDFParser
from ..parsers.docx_parser import DocxParser
from ..parsers.llama_parser import LlamaParser
from ..config.settings import Settings

load_dotenv()
logging.basicConfig(level=logging.INFO)

class LLMService:
    def __init__(self, model: str):
        self.model = model
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.llm = self._initialize_llm()
        self.current_month_year = datetime.today().strftime("%B %Y")
        self.good_characteristics = []
        self.use_example_resumes = False  # New flag for using example resumes

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
                    n=1
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
        self.current_job_description = job_description
        
        if good_resumes_dir:
            logging.info(f"Processing example resumes from: {good_resumes_dir}")
            good_text = self._read_resumes_from_dir(good_resumes_dir)
            
            if good_text:
                # Count number of resumes being analyzed
                resume_count = good_text.count("=== Resume:")
                logging.info(f"Analyzing characteristics from {resume_count} good resumes")
                
                # Extract characteristics from combined resumes
                self.good_characteristics = self._analyze_characteristics(good_text, "good")
                
                if self.good_characteristics:
                    self.use_example_resumes = True
                    logging.info(f"Successfully extracted {len(self.good_characteristics)} characteristics")
                    logging.info("=== Extracted Good Resume Characteristics ===")
                    for i, char in enumerate(self.good_characteristics, 1):
                        logging.info(f"{i}. {char}")
                    logging.info("=" * 45)  # Visual separator for log readability
                else:
                    logging.warning("No characteristics extracted from good resumes")
                    self.use_example_resumes = False
            else:
                logging.warning("No content extracted from example resumes")
                self.use_example_resumes = False
                self.good_characteristics = []

    def _read_resumes_from_dir(self, directory: str) -> str:
        """Read and concatenate resumes from directory with a limit"""
        MAX_SAMPLE_RESUMES = 5  # Maximum number of sample resumes to process
        
        if not os.path.exists(directory):
            logging.warning(f"Directory not found: {directory}")
            return ""
            
        resumes_text = []
        try:
            pdf_parser = PyPDFParser()
            docx_parser = DocxParser()
            llama_parser = LlamaParser()  # Initialize LlamaParse
            
            # Get all files and sort them
            files = [f for f in os.listdir(directory) 
                    if f.lower().endswith(('.pdf', '.doc', '.docx'))]
            files.sort()
            
            # Limit number of files
            files = files[:MAX_SAMPLE_RESUMES]
            logging.info(f"Processing {len(files)} sample resumes (maximum {MAX_SAMPLE_RESUMES})")
            
            for filename in files:
                file_path = os.path.join(directory, filename)
                content = None
                
                try:
                    if filename.lower().endswith('.pdf'):
                        # Try PyPDF first
                        content = pdf_parser.parse(file_path)
                        
                        # If PyPDF fails or returns empty content, try LlamaParse
                        if not content or not content.get("content") or not content.get("content").strip():
                            logging.info(f"PyPDF parser failed for {filename}, trying LlamaParse")
                            content = llama_parser.parse(file_path)
                            
                    elif filename.lower().endswith(('.doc', '.docx')):
                        # Try docx parser first
                        content = docx_parser.parse(file_path)
                        
                        # If docx parser fails, try LlamaParse
                        if not content or not content.get("content") or not content.get("content").strip():
                            logging.info(f"DOCX parser failed for {filename}, trying LlamaParse")
                            content = llama_parser.parse(file_path)
                    
                    # Add successfully parsed content
                    if content and content.get("content") and content.get("content").strip():
                        resumes_text.append(f"=== Resume: {filename} ===\n{content['content']}\n")
                        logging.info(f"Successfully extracted content from {filename} using {content.get('parser_used', 'unknown parser')}")
                    else:
                        logging.warning(f"Failed to extract content from {filename} with all parsers")
                        
                except Exception as e:
                    logging.error(f"Error processing {filename}: {str(e)}")
                    
            # Combine all resume texts
            combined_text = "\n\n".join(resumes_text)
            logging.info(f"Successfully combined {len(resumes_text)} resumes")
            
            return combined_text
                
        except Exception as e:
            logging.error(f"Error reading directory {directory}: {str(e)}")
            return ""

    def analyze_resume(self, resume_text: str, job_description: str, 
                      scoring_weights: Dict[str, float], priority_order: str) -> Dict:
        try:
            # Debug logging at the start
            logging.info(f"Starting analyze_resume with use_example_resumes: {self.use_example_resumes}")
            logging.info(f"Number of good characteristics: {len(self.good_characteristics)}")
            
            # Select template based on whether good resumes were provided
            if self.use_example_resumes and self.good_characteristics:
                logging.info("Using GOOD template with characteristics")
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
                logging.info("Using STANDARD template")
                template = PROMPT_TEMPLATE
                input_vars = {
                    "current_month_year": self.current_month_year,
                    "criteria_list": self._generate_criteria_list(scoring_weights),
                    "priority_order": priority_order,
                    "job_desc": job_description,
                    "resume": resume_text
                }

            # Create prompt template with correct variables
            prompt = PromptTemplate(
                template=template,
                input_variables=list(input_vars.keys())
            )

            # Create and execute chain
            chain = prompt | self.llm | StrOutputParser()
            result = chain.invoke(input_vars)

            return clean_llm_output(result)

        except Exception as e:
            logging.error(f"Error in analyze_resume: {str(e)}")
            return self._generate_error_response()

    def _generate_error_response(self):
        """Generate a standardized error response"""
        return {
            "information": {},
            "evaluation": {
                "total_score": 0,
                "explanation": "Error analyzing resume"
            },
            "processing_time": 0
        }