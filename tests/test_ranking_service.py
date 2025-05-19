import pytest
import pandas as pd
from app.services.ranking_service import RankingService
import os
from unittest.mock import patch, MagicMock

SAMPLE_DIR = "tests/samples"  # Make sure this directory exists with sample files

class TestRankingService:
    @pytest.fixture
    def ranking_service(self):
        return RankingService(model="gpt-4o")

    @pytest.fixture
    def sample_resume_dir(self):
        return SAMPLE_DIR  # Use actual directory with sample resumes like PDFs or DOCXs

    @pytest.fixture
    def sample_job_description(self):
        return """
        Senior Software Engineer Position
        Required Skills: Python, SQL, AWS
        Experience: 5+ years
        Education: BS in Computer Science or related field
        """

    def test_process_resumes_empty_directory(self, ranking_service, sample_job_description):
        # Simulate an empty directory scenario with a temp empty dir
        empty_dir = "tests/samples/empty"  # You can create this manually or check/create in test
        os.makedirs(empty_dir, exist_ok=True)

        result = ranking_service.process_resumes(empty_dir, sample_job_description)

        assert isinstance(result, pd.DataFrame)
        assert result.empty
        assert list(result.columns) == [
            'Rank', 'name', 'total_score', 'skills', 'experience_years',
            'phone', 'email', 'location_info', 'File', 'processing_time'
        ]

    @patch('app.services.ranking_service.PyPDFParser')
    @patch('app.services.ranking_service.LLMService')
    def test_process_resumes_with_files(
        self, mock_llm_service, mock_pdf_parser,
        ranking_service, sample_resume_dir, sample_job_description
    ):
        sample_file = os.path.join(sample_resume_dir, "Cutshort-Dnyaneshwar-Mali-Tachila-updated-9CHg 1.pdf")
        assert os.path.exists(sample_file), f"{sample_file} not found"

        # Mock parser response
        mock_pdf_parser.return_value.parse.return_value = {
            "content": "Sample resume content",
            "parser_used": "PyPDF2"
        }

        # Mock LLM service response
        mock_llm_service.return_value.analyze_resume.return_value = {
            "extracted_info": {
                "name": "John Doe",
                "experience_years": 5.5,
                "skills": ["Python", "SQL"],
                "education": ["BS Computer Science"],
                "certifications": [],
                "location": "New York",
                "email": "john@example.com",
                "phone": "123-456-7890"
            },
            "evaluation": {
                "skills_match": 85,
                "experience": 90,
                "education": 80,
                "certifications": 0,
                "location": 100,
                "total_score": 85.5
            },
            "processing_time": 1.5
        }

        result = ranking_service.process_resumes(sample_resume_dir, sample_job_description)

        assert isinstance(result, pd.DataFrame)
        assert not result.empty
        assert "Rank" in result.columns
        assert "total_score" in result.columns
        assert result["Rank"].iloc[0] == 1
        assert len(result) >= 1  # If multiple resumes exist in samples, len may be >1

    def test_process_resumes_with_invalid_weights(self, ranking_service, sample_job_description):
        """Test process_resumes with invalid scoring weights"""
        invalid_weights = {
            "skills_match": 0.5,
            "experience": 0.6  # Total > 1.0
        }
        ranking_service.scoring_weights = invalid_weights
        
        result = ranking_service.process_resumes("/test/dir", sample_job_description)
        assert result.empty

    @patch('glob.glob')
    def test_process_resumes_with_unsupported_files(self, mock_glob, ranking_service, 
        sample_job_description):
        """Test process_resumes with unsupported file types"""
        mock_glob.return_value = ["test.txt", "test.jpg"]
        result = ranking_service.process_resumes("/test/dir", sample_job_description)
        assert result.empty

    @patch('app.services.ranking_service.LLMService')
    @patch('os.path.exists')
    def test_analyze_example_resumes_error(self, mock_exists, mock_llm_service, ranking_service):
        """Test analyze_example_resumes error handling"""
        # Mock directory existence
        mock_exists.return_value = True
        
        # Create mock LLM service instance
        mock_llm_instance = MagicMock()
        mock_llm_instance.analyze_example_resumes.side_effect = Exception("Test error")
        mock_llm_service.return_value = mock_llm_instance
        
        # Replace ranking service's LLM instance with our mock
        ranking_service.llm_service = mock_llm_instance
        
        # Call the method
        ranking_service.analyze_example_resumes("good/dir", "bad/dir")
        
        # Verify the method was called
        mock_llm_instance.analyze_example_resumes.assert_called_once_with(
            "good/dir", "bad/dir"
        )
