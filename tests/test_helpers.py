import pytest
from datetime import datetime
from app.utils.helpers import calculate_experience_years, validate_file_extension, format_phone_number
from app.utils.helpers import clean_llm_output
class TestHelpers:
    def test_calculate_experience_years(self):
        # Test fixed dates
        assert calculate_experience_years("2020-01", "2024-01") == 4.0
        assert calculate_experience_years("2020-01", "2020-07") == 0.5
        
        # Test with present date
        result = calculate_experience_years("2020-01", "present")
        current_year = datetime.now().year
        expected_min = current_year - 2020
        assert isinstance(result, float)
        assert result >= expected_min
        
        # Test invalid dates
        with pytest.raises(ValueError):
            calculate_experience_years("invalid", "2024-01")
            
    def test_validate_file_extension(self):
        # Test valid extensions
        assert validate_file_extension("test.pdf") == True
        assert validate_file_extension("test.docx") == True
        assert validate_file_extension("TEST.PDF") == True
        assert validate_file_extension("test.DOCX") == True
        
        # Test invalid extensions
        assert validate_file_extension("test.txt") == False
        assert validate_file_extension("test") == False
        assert validate_file_extension(".pdf") == True
        assert validate_file_extension("test.doc") == False
        
    def test_format_phone_number(self):
        """Test various phone number formats"""
        # US/Canada formats
        assert format_phone_number("1234567890") == "+1-123-456-7890"
        assert format_phone_number("+1-123-456-7890") == "+1-123-456-7890"
        assert format_phone_number("123-456-7890") == "+1-123-456-7890"
        assert format_phone_number("11234567890") == "+1-123-456-7890"
        
        # Invalid formats
        assert format_phone_number("invalid") == "invalid"
        assert format_phone_number("123") == "invalid"
        assert format_phone_number("") == "invalid"

    def test_clean_llm_output_invalid_json(self):
        """Test clean_llm_output with invalid JSON"""
        result = clean_llm_output("Invalid JSON {")
        assert result == {}

    def test_clean_llm_output_no_json(self):
        """Test clean_llm_output with no JSON content"""
        result = clean_llm_output("No JSON here")
        assert result == {}

    def test_clean_llm_output_with_code_blocks(self):
        """Test clean_llm_output with code blocks"""
        input_text = '''```json
        {"key": "value"}
        ```'''
        result = clean_llm_output(input_text)
        assert result == {"key": "value"}

    def test_format_phone_number_international(self):
        """Test international phone number formats"""
        # UK numbers
        assert format_phone_number("442012345678") == "+44-201-234-5678"
        assert format_phone_number("+442012345678") == "+442012345678"
        
        # Indian numbers
        assert format_phone_number("919876543210") == "+91-98765-43210"
        assert format_phone_number("+919876543210") == "+919876543210"
        
        # Generic international numbers
        assert format_phone_number("123456789012") == "+12-345-678-9012"
        assert format_phone_number("12345678") == "+12345678"

    @pytest.mark.parametrize("test_input,expected", [
        ("test.PDF", True),
        ("test.DOCX", True),
        ("test.exe", False),
        ("test", False),
        ("", False),
    ])
    def test_validate_file_extension_parametrized(self, test_input, expected):
        """Parametrized tests for validate_file_extension"""
        assert validate_file_extension(test_input) == expected

    def test_calculate_experience_years_edge_cases(self):
        """Test edge cases for experience calculation"""
        # Test exact month differences
        assert calculate_experience_years("2020-01", "2020-02") == 0.1
        assert calculate_experience_years("2020-12", "2021-01") == 0.1
        
        # Test invalid date formats
        with pytest.raises(ValueError):
            calculate_experience_years("2020", "2021")
        with pytest.raises(ValueError):
            calculate_experience_years("2020-13", "2021-01")
        with pytest.raises(ValueError):
            calculate_experience_years("2020-01", "invalid")

    def test_clean_llm_output_edge_cases(self):
        """Test edge cases for LLM output cleaning"""
        # Test empty input
        assert clean_llm_output("") == {}
        
        # Test multiple JSON objects
        result = clean_llm_output('{"a": 1} {"b": 2}')
        assert result == {"a": 1}
        
        # Test nested JSON
        result = clean_llm_output('{"a": {"b": 2}}')
        assert result == {"a": {"b": 2}}
        
        # Test malformed JSON
        assert clean_llm_output("{a: 1}") == {}