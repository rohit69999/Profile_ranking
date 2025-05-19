import pytest
from app.services.llm_service import LLMService
from unittest.mock import patch, MagicMock

class TestLLMService:
    @pytest.fixture
    def llm_service(self):
        return LLMService(model="gpt-4o-mini")
        
    @pytest.fixture
    def sample_resume_text(self):
        return """
        John Doe
        Software Engineer
        email@example.com
        (123) 456-7890
        
        Experience:
        - Senior Software Engineer, Tech Corp (2020-present)
        - Software Developer, Dev Inc (2018-2020)
        
        Skills: Python, Java, SQL
        Education: BS Computer Science
        """
        
    @pytest.fixture
    def sample_job_description(self):
        return """
        Looking for a Senior Software Engineer
        Required Skills: Python, SQL, AWS
        Experience: 5+ years
        Education: BS in Computer Science or related field
        """
        
    @pytest.fixture
    def sample_ranking_priority(self):
        return [
            "skills_match",
            "experience",
            "education",
            "certifications",
            "location"
        ]
        
    @pytest.fixture
    def sample_scoring_weights(self):
        return {
            "skills_match": 0.35,
            "experience": 0.25,
            "education": 0.20,
            "certifications": 0.10,
            "location": 0.10
        }

    def test_analyze_resume(self, llm_service, sample_resume_text, sample_job_description):
        scoring_weights = {
            "skills_match": 0.35,
            "experience": 0.25,
            "education": 0.20,
            "certifications": 0.10,
            "location": 0.10
        }
        
        ranking_priority = [
            "skills_match",
            "experience",
            "education",
            "certifications",
            "location"
        ]
        
        result = llm_service.analyze_resume(
            sample_resume_text,
            sample_job_description,
            scoring_weights,
            ranking_priority
        )
        
        assert isinstance(result, dict)
        assert "extracted_info" in result
        assert "evaluation" in result
        assert "processing_time" in result
        
        info = result["extracted_info"]
        evaluation = result["evaluation"]
        
        assert isinstance(info, dict)
        assert isinstance(evaluation, dict)
        assert isinstance(result["processing_time"], float)
        
        # Check required fields
        assert "name" in info
        assert "experience_years" in info
        assert "skills" in info
        assert "education" in info
        assert isinstance(info["skills"], list)
        
        assert "skills_match" in evaluation
        assert "experience" in evaluation
        assert "education" in evaluation
        assert "total_score" in evaluation
        
        # Check score ranges
        assert 0 <= evaluation["skills_match"] <= 100
        assert 0 <= evaluation["experience"] <= 100
        assert 0 <= evaluation["education"] <= 100
        assert 0 <= evaluation["total_score"] <= 100
    
    def test_analyze_resume_invalid_weights(self, llm_service, sample_resume_text, sample_job_description, sample_ranking_priority):
        invalid_weights = {
            "skills_match": 0.5,
            "experience": 0.6  # Total > 1.0
        }
    
        with pytest.raises(ValueError) as exc_info:
            llm_service.analyze_resume(
                sample_resume_text,
                sample_job_description,
                invalid_weights,
                sample_ranking_priority
            )
        assert "weights must sum to 1.0" in str(exc_info.value)

    def test_analyze_resume_empty_input(self, llm_service, sample_ranking_priority, sample_scoring_weights):
        with pytest.raises(ValueError) as exc_info:
            llm_service.analyze_resume(
                "",
                "job description",
                sample_scoring_weights,
                sample_ranking_priority
            )
        assert "Resume text cannot be empty" in str(exc_info.value)

    def test_analyze_resume_empty_job_description(self, llm_service, sample_resume_text, sample_ranking_priority, sample_scoring_weights):
        """Test that empty job description raises ValueError"""
        with pytest.raises(ValueError) as exc_info:
            llm_service.analyze_resume(
                sample_resume_text,
                "",
                sample_scoring_weights,
                sample_ranking_priority
            )
        assert "Job description cannot be empty" in str(exc_info.value)

    @patch('app.services.llm_service.ChatOpenAI')
    def test_initialize_llm_openai(self, mock_chat_openai, llm_service):
        """Test LLM initialization with OpenAI"""
        llm_service.model = "gpt-4o"
        llm_service._initialize_llm()
        mock_chat_openai.assert_called_once_with(
            model="gpt-4o",
            api_key=llm_service.gpt_api_key,
            temperature=0.5
        )

    @patch('app.services.llm_service.ChatGroq')
    def test_initialize_llm_groq(self, mock_chat_groq, llm_service):
        """Test LLM initialization with Groq"""
        llm_service.model = "deepseek-r1-distill-llama-70b"
        llm_service._initialize_llm()
        mock_chat_groq.assert_called_once_with(
            model="deepseek-r1-distill-llama-70b",
            api_key=llm_service.groq_api_key
        )

    def test_generate_criteria_list(self, llm_service, sample_scoring_weights):
        """Test criteria list generation"""
        result = llm_service._generate_criteria_list(sample_scoring_weights)
        expected = (
            "- Skills_match: 35.0%\n"
            "- Experience: 25.0%\n"
            "- Education: 20.0%\n"
            "- Certifications: 10.0%\n"
            "- Location: 10.0%"
        )
        assert result == expected

    @patch('app.services.llm_service.PromptTemplate')
    @patch('app.services.llm_service.StrOutputParser')
    def test_analyze_characteristics_good(self, mock_str_parser, mock_prompt, llm_service):
        """Test analysis of good resume characteristics"""
        # Setup mock response
        mock_response = "- Clear contact information\n- Relevant technical skills\n- Quantified achievements"
        
        # Create a real chain that will return our mock response
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        
        # Setup the chain components
        mock_prompt_instance = MagicMock()
        mock_prompt.return_value = mock_prompt_instance
        
        # Make the chain construction work correctly
        mock_chain = mock_prompt_instance | mock_llm | mock_str_parser
        mock_chain.invoke.return_value = mock_response
        
        # Set the job description
        llm_service.current_job_description = "Sample job description"
        
        # Call the method
        result = llm_service._analyze_characteristics("Sample resume text", "good")
        
        assert result == [
            "Clear contact information",
            "Relevant technical skills",
            "Quantified achievements"
        ]

    @patch('app.services.llm_service.PromptTemplate')
    @patch('app.services.llm_service.StrOutputParser')
    def test_analyze_characteristics_bad(self, mock_str_parser, mock_prompt, llm_service):
        """Test analysis of bad resume characteristics"""
        # Setup mock response
        mock_response = "- Spelling errors\n- Irrelevant experience\n- Missing contact info"
        
        # Create a real chain that will return our mock response
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        
        # Setup the chain components
        mock_prompt_instance = MagicMock()
        mock_prompt.return_value = mock_prompt_instance
        
        # Make the chain construction work correctly
        mock_chain = mock_prompt_instance | mock_llm | mock_str_parser
        mock_chain.invoke.return_value = mock_response
        
        # Set the job description
        llm_service.current_job_description = "Sample job description"
        
        # Call the method
        result = llm_service._analyze_characteristics("Sample resume text", "bad")
        
        assert result == [
            "Spelling errors",
            "Irrelevant experience",
            "Missing contact info"
        ]

    def test_invalid_llm_response(self, llm_service, sample_resume_text, sample_job_description, 
                                sample_ranking_priority, sample_scoring_weights):
        """Test handling of invalid LLM response format"""
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = {"invalid": "response"}
        llm_service.llm = mock_chain

        result = llm_service.analyze_resume(
            sample_resume_text,
            sample_job_description,
            sample_scoring_weights,
            sample_ranking_priority
        )

        assert "Error analyzing resume" in result["evaluation"]["explanation"]
        assert result["evaluation"]["total_score"] == 0
        assert isinstance(result["processing_time"], float)

    @patch('app.services.llm_service.LLMService._initialize_llm')
    def test_llm_service_init_missing_api_keys(self, mock_init_llm):
        """Test LLMService initialization with missing API keys"""
        # Configure mock to raise ValueError
        mock_init_llm.side_effect = ValueError("Error initializing LLM: OpenAI API key not found")
        
        # Test initialization
        with pytest.raises(ValueError) as exc_info:
            service = LLMService(model="gpt-4o")
        
        # Verify error message
        assert "Error initializing LLM" in str(exc_info.value)
        assert "OpenAI API key not found" in str(exc_info.value)

    @patch('app.services.llm_service.ChatOpenAI')
    def test_analyze_resume_with_empty_ranking_priority(self, mock_chat_openai, llm_service, 
        sample_resume_text, sample_job_description, sample_scoring_weights):
        """Test analyze_resume with empty ranking priority"""
        result = llm_service.analyze_resume(
            sample_resume_text,
            sample_job_description,
            sample_scoring_weights,
            []  # Empty ranking priority
        )
        assert isinstance(result, dict)
        assert "evaluation" in result

    @patch('os.path.exists')
    @patch('app.services.llm_service.DocxParser')
    @patch('app.services.llm_service.PyPDFParser')
    def test_read_resumes_from_dir_empty(self, mock_pdf_parser, mock_docx_parser, 
        mock_exists, llm_service):
        """Test reading from empty directory"""
        mock_exists.return_value = True
        result = llm_service._read_resumes_from_dir("/empty/dir")
        assert result == ""

    @patch('os.listdir')
    def test_read_resumes_from_nonexistent_dir(self, mock_listdir, llm_service):
        """Test reading from nonexistent directory"""
        mock_listdir.side_effect = FileNotFoundError()
        result = llm_service._read_resumes_from_dir("/nonexistent/dir")
        assert result == ""