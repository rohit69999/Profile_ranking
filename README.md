# AI-Powered Resume Ranker

An intelligent resume ranking system that automatically analyzes and scores resumes based on job requirements using AI. Built with Streamlit and powered by LLM for accurate candidate matching.

![Resume Ranker Demo](path_to_demo_image.gif)

## 🌟 Features

- **Automated Resume Analysis**: Process multiple resumes (PDF, DOC, DOCX) simultaneously
- **AI-Powered Matching**: Advanced matching against job requirements using LLM
- **Parallel Processing**: Fast processing with multi-threading support
- **Interactive UI**: Clean, modern interface built with Streamlit
- **Detailed Analytics**: 
  - Match scoring
  - Experience analysis
  - Location mapping
  - Contact information extraction
- **Export Options**: Download results in CSV or Excel format

## 🚀 Getting Started

### Prerequisites

- Python 3.10 or higher
- Groq API key (for LLM access)

### Installation

1. Clone the repository:
```bash
git clone https://Applied-GenAI@dev.azure.com/Applied-GenAI/GenAI_Internal/_git/profile_ranking_system
cd profile_ranking_system
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install required packages:
```bash
pip install -r requirements.txt
```

### Configuration

1. Create a `.env` file in the project root:
```env
GROQ_API_KEY=your_api_key_here
LLAMA_CLOUD_API_KEY=your_api_key_here
OPENAI_API_KEY=your_api_key_here
```

## 💻 Usage

1. Start the Streamlit app:
```bash
streamlit run streamlit_ui.py
```

2. Open your browser and navigate to `http://localhost:8501`

3. Follow these steps in the UI:
   - Enter your API key
   - Upload resume files (PDF, DOC, DOCX supported)
   - Enter the job description
   - Click "Start Processing"
   - View results and download reports

## 📁 Project Structure

```

profile_ranking_system/
├── app/
│   ├── __init__.py
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py         # Configuration settings and constants
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── base_parser.py      # Abstract base class for parsers
│   │   ├── pypdf_parser.py     # PyPDF2 implementation
│   │   ├── docx_parser.py      # DOCX parser implementation
│   │   └── llama_parser.py     # LlamaParse implementation
│   ├── models/
│   │   ├── __init__.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── llm_service.py     # LLM integration (OpenAI/Groq)
│   │   └── ranking_service.py # Core ranking logic
│   └── utils/
│       ├── __init__.py
│       └── helpers.py         # Common utility functions
├── streamlit_ui.py                     # Streamlit interface
├── requirements.txt
└── README.md
```


## 🔍 Sample Output

The system generates a DataFrame with the following columns:
- S.No
- Name
- Experience (Years)
- Location
- Email
- Phone
- Match Score
- File

# Build and Test
TODO: Describe and show how to build your code and run the tests. 

# Contribute
TODO: Explain how other users and developers can contribute to make your code better. 

If you want to learn more about creating good readme files then refer the following [guidelines](https://docs.microsoft.com/en-us/azure/devops/repos/git/create-a-readme?view=azure-devops). You can also seek inspiration from the below readme files:
- [ASP.NET Core](https://github.com/aspnet/Home)
- [Visual Studio Code](https://github.com/Microsoft/vscode)
- [Chakra Core](https://github.com/Microsoft/ChakraCore)