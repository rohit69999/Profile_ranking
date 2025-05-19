from setuptools import setup, find_packages

setup(
    name="profile_ranking_system",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "streamlit>=1.32.0",
        "pandas>=2.0.0",
        "PyPDF2>=3.0.0",
        "python-docx>=1.0.0",
        "docx2txt>=0.8",
        "langchain>=0.1.0",
        "langchain-groq>=0.1.0",
        "python-dotenv>=1.0.0",
        "openpyxl>=3.1.2",
        "watchdog>=3.0.0",
        "openai",
        "langchain-openai",
        "llama-parse"
    ]
)