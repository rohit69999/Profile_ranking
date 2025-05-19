import PyPDF2
import logging
import os
from typing import Dict
from .base_parser import BaseParser

class PyPDFParser(BaseParser):
    def parse(self, file_path: str) -> Dict[str, str]:
        if not os.path.exists(file_path):
            logging.error(f"File not found: {file_path}")
            return {"content": "", "parser_used": "PyPDF2", "error": "File not found"}
            
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = "\n".join(page.extract_text() for page in pdf_reader.pages)
                
                if not text.strip():
                    logging.warning(f"No text content extracted from {file_path}")
                    return {"content": "", "parser_used": "PyPDF2", "error": "No text content extracted"}
                    
                return {
                    "content": text,
                    "parser_used": "PyPDF2"
                }
                
        except Exception as e:
            logging.error(f"Error parsing PDF {file_path}: {str(e)}")
            return {"content": "", "parser_used": "PyPDF2", "error": str(e)}