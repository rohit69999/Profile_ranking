import pytest
import os
from app.parsers.pypdf_parser import PyPDFParser
from app.parsers.docx_parser import DocxParser
from app.parsers.llama_parser import LlamaParser
from app.parsers.base_parser import BaseParser
from unittest.mock import patch, MagicMock

SAMPLE_DIR = "tests/samples"  # Adjust based on actual location

class TestParsers:

    @pytest.fixture
    def sample_pdf_path(self):
        return os.path.join(SAMPLE_DIR, "Cutshort-Dnyaneshwar-Mali-Tachila-updated-9CHg 1.pdf")

    @pytest.fixture
    def sample_docx_path(self):
        return os.path.join(SAMPLE_DIR, "Naukri_GodhaSaikumar[5y_5m].docx")

    def test_pdf_parser(self, sample_pdf_path):
        parser = PyPDFParser()
        result = parser.parse(sample_pdf_path)

        assert isinstance(result, dict)
        assert "content" in result
        assert "parser_used" in result
        assert result["parser_used"] == "PyPDF2"
        assert result["content"]  # Ensure content is not empty

    def test_docx_parser(self, sample_docx_path):
        parser = DocxParser()
        result = parser.parse(sample_docx_path)

        assert isinstance(result, dict)
        assert "content" in result
        assert "parser_used" in result
        assert result["parser_used"] == "docx2txt"
        assert result["content"]  # Ensure content is not empty

    def test_invalid_file_pdf_parser(self):
        parser = PyPDFParser()
        result = parser.parse("nonexistent.pdf")

        assert isinstance(result, dict)
        assert result["content"] == ""
        assert result["parser_used"] == "PyPDF2"

    def test_invalid_file_docx_parser(self):
        parser = DocxParser()
        result = parser.parse("nonexistent.docx")

        assert isinstance(result, dict)
        assert result["content"] == ""
        assert result["parser_used"] == "docx2txt"

class TestLlamaParser:
    def test_llama_parser_successful_parse(self, mocker):
        # Mock LlamaParse
        mock_llama = mocker.patch('llama_parse.LlamaParse')
        mock_doc = mocker.Mock()
        mock_doc.text = "Test resume content"
        mock_llama.return_value.load_data.return_value = [mock_doc]
        
        parser = LlamaParser()
        result = parser.parse("test.pdf")
        
        assert result["content"] == "Test resume content"
        assert result["parser_used"] == "LlamaParse"
        assert "error" not in result

    def test_llama_parser_api_error(self, mocker):
        # Mock LlamaParse with error
        mock_llama = mocker.patch('llama_parse.LlamaParse')
        mock_llama.return_value.load_data.side_effect = Exception("API Error")
        
        parser = LlamaParser()
        result = parser.parse("test.pdf")
        
        assert "error" in result
        assert result["content"] == ""
        assert result["parser_used"] == "LlamaParse"

    def test_llama_parser_invalid_file(self):
        parser = LlamaParser()
        result = parser.parse("nonexistent.pdf")
        
        assert "error" in result
        assert "File not found" in result["error"]
        assert result["content"] == ""
        assert result["parser_used"] == "LlamaParse"

class TestBaseParser:
    def test_base_parser_abstract(self):
        """Test that BaseParser cannot be instantiated directly"""
        with pytest.raises(TypeError) as exc_info:
            BaseParser()
        assert "Can't instantiate abstract class BaseParser" in str(exc_info.value)

    def test_base_parser_implementation(self):
        """Test concrete implementation of BaseParser"""
        class ConcreteParser(BaseParser):
            def parse(self, file_path: str):
                return {"content": "test", "parser_used": "test"}
        
        parser = ConcreteParser()
        result = parser.parse("test.pdf")
        assert result["content"] == "test"
        assert result["parser_used"] == "test"
