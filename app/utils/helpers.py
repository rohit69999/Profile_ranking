import json
from datetime import datetime
import re
from typing import Dict
import logging

def clean_llm_output(text: str) -> dict:
    """Clean and parse LLM output to extract JSON."""
    if not text:
        return {}
        
    try:
        # First try to find JSON in code blocks
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            try:
                json_str = json_match.group(1).strip()
                return json.loads(json_str)
            except json.JSONDecodeError:
                logging.error(f"Failed to parse JSON from code block: {json_str}")
                
        # Try to find raw JSON object
        json_pattern = r'(\{(?:[^{}]|(?R))*\})'
        matches = re.finditer(json_pattern, text, re.DOTALL)
        for match in matches:
            try:
                json_str = match.group(1).strip()
                return json.loads(json_str)
            except json.JSONDecodeError:
                continue
                
        # Try direct JSON parsing as last resort
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
                
    except Exception as e:
        logging.error(f"Error cleaning LLM output: {str(e)}")
        logging.debug(f"Raw text: {text}")
        
    return {}

def calculate_experience_years(start_date: str, end_date: str) -> float:
    """Calculate years of experience between two dates."""
    start = datetime.strptime(start_date, "%Y-%m")
    
    if end_date.lower() == "present":
        end = datetime.now()
    else:
        end = datetime.strptime(end_date, "%Y-%m")
    
    difference = end - start
    return round(difference.days / 365.25, 1)

def validate_file_extension(filename: str) -> bool:
    """Validate if the file extension is supported."""
    allowed_extensions = {".pdf", ".docx"}
    file_extension = "." + filename.split(".")[-1].lower() if "." in filename else ""
    return file_extension in allowed_extensions

def format_phone_number(phone: str) -> str:
    """Format phone number based on country code patterns."""
    # If already in international format with +, return as is
    if phone.startswith('+'):
        return phone
        
    # Remove any non-digit characters
    digits = re.sub(r'\D', '', phone)
    
    if not digits:
        return "invalid"
        
    # Handle various country formats
    if len(digits) == 10:  # US/Canada format
        return f"+1-{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    elif len(digits) == 11:
        if digits.startswith('1'):  # US/Canada with country code
            return f"+{digits[0]}-{digits[1:4]}-{digits[4:7]}-{digits[7:]}"
        else:  # Other 11-digit formats
            return f"+{digits}"
    elif len(digits) == 12:  # International format (e.g., UK/India)
        return f"+{digits}"  # Return as-is for international numbers
    elif len(digits) >= 8:  # Generic international format
        return f"+{digits}"
    
    return "invalid"