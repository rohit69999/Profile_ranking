import docx2txt
import logging
from typing import Dict
from .base_parser import BaseParser

class DocxParser(BaseParser):
    def parse(self, file_path: str) -> Dict[str, str]:
        try:
            text = docx2txt.process(file_path)
            return {"content": text, "parser_used": "docx2txt"}
        except Exception as e:
            logging.warning(f"Error reading DOCX {file_path}: {str(e)}")
            return {"content": "", "parser_used": "docx2txt"}