import os
from llama_parse import LlamaParse
import logging
from typing import Dict
from .base_parser import BaseParser
from dotenv import load_dotenv
import streamlit as st

load_dotenv()

class LlamaParser(BaseParser):
    def parse(self, file_path: str) -> Dict[str, str]:
        """Parse document using LlamaParse."""
        try:
            # api_key = os.getenv("LLAMA_CLOUD_API_KEY")
            api_key = st.secrets ["LLAMA_CLOUD_API_KEY"]
            
            if not api_key:
                raise ValueError("Missing Llama Cloud API Key")

            parser = LlamaParse(api_key=api_key, result_type="text")
            
            # Process with LlamaParse - using file_path instead of file_name
            documents = parser.load_data(file_path=file_path)

            if not documents:
                logging.warning(f"No content extracted from {file_path}")
                return {"content": "", "parser_used": "LlamaParse"}

            # Combine text from all pages
            text = "\n".join(str(doc.text) for doc in documents if hasattr(doc, 'text'))
            
            if not text.strip():
                logging.warning(f"Extracted empty content from {file_path}")
                return {"content": "", "parser_used": "LlamaParse"}

            return {
                "content": text,
                "parser_used": "LlamaParse"
            }

        except Exception as e:
            logging.error(f"LlamaParse failed to read {file_path}: {str(e)}")
            return {"content": "", "parser_used": "LlamaParse"}