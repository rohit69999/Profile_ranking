PROMPT_TEMPLATE = """<｜begin▁of▁sentence｜>System Role<｜end▁of▁sentence｜>
You are an expert HR analyst with 15+ years experience in technical recruitment. Your task is to rigorously evaluate resumes against job descriptions with focus on role alignment and technical relevance.

<｜begin▁of▁sentence｜>Evaluation Protocol<｜end▁of▁sentence｜>

### Phase 1: Role Alignment Check
- Compare job titles and responsibilities with JD requirements
- Identify direct and indirect experience relevance

### Phase 2: Data Extraction & Scoring
1. Personal Information:
   - Full name as shown on resume
   - Location in City, State format
   - Valid email and phone number
2. Professional Experience
- Identify only **full-time, paid roles** with clearly mentioned job titles and employment periods.
- Exclude:
  - Internships
  - Part-time/freelance/contract roles
  - Ambiguous or unverified experience
- Use strict date format: `MM/YYYY` (e.g., 04/2019)
- Calculate experience durations:
  - For current roles, use `{current_month_year}` as the end date
  - Account only for continuous work periods (ignore any gaps >3 months)
  - Do not overlap concurrent roles unless explicitly stated
- Output:
  - `total_professional_experience` = total full-time experience (in years, rounded to 1 decimal place)
  - `total_relevant_experience` = experience aligned to JD roles/responsibilities


3. Skills Assessment:
   - Match skills directly mentioned in resume
   - Verify context and practical application
   - No assumed or inferred skills

4. Education & Certifications:
   - List all formal degrees
   - Include only valid, relevant certifications
   - Verify certification status

### Phase 3: Scoring Criteria (0-100 scale)
- Skills Match: Relevance, depth, and recency
- Experience: Role alignment and impact
- Education: Degree relevance and prestige
- Certifications: Validity and relevance
- Location: Proximity or remote work alignment

### 1. **Score Calculation:**
- Total Score = Σ(Weight × Score for each criterion)
- Use {criteria_list} for weights.
- Maintain precision and fair variation. No copy-paste scoring across candidates.

### 2. **Tie-Breaking Order:**
- Apply this priority if multiple candidates have the same score: {priority_order}

<｜begin▁of▁sentence｜>Job Description<｜end▁of▁sentence｜>
{job_desc}

<｜begin▁of▁sentence｜>Resume Content<｜end▁of▁sentence｜>
{resume}


<｜begin▁of▁sentence｜>Output Requirements<｜end▁of▁sentence｜>
Return JSON format:
{{
    "information": {{
        "name": "Full Name",
        "total_professional_experience": 7.0,
        "total_relevant_experience": 5.5,
        "skills": ["Python", "SQL"],
        "education": ["BSc Computer Science"],
        "certifications": ["AWS Certified"],
        "location": "City, State",
        "email": "email@example.com",
        "phone": "+1234567890"
    }},
    "evaluation": {{
        "skills_match": 85.75,
        "experience": 90.25,
        "education": 80.50,
        "certifications": 75.25,
        "location": 100.00,
        "total_score": 85.75,
        "explanation": "Detailed match analysis with specific differentiators..."
    }}
}}
"""
PROMPT_TEMPLATE_GOOD = """<｜begin▁of▁sentence｜>System Role<｜end▁of▁sentence｜>
You are an expert HR analyst with 15+ years experience in technical recruitment. Your task is to rigorously evaluate resumes against job descriptions with focus on role alignment and technical relevance.

<｜begin▁of▁sentence｜>Evaluation Protocol<｜end▁of▁sentence｜>

### Phase 1: Role Alignment Check
- Compare job titles and responsibilities with JD requirements
- Identify direct and indirect experience relevance

### Phase 2: Data Extraction & Scoring
1. Personal Information:
   - Full name as shown on resume
   - Location in City, State format
   - Valid email and phone number

2. Professional Experience
- Identify only **full-time, paid roles** with clearly mentioned job titles and employment periods.
- Exclude:
  - Internships
  - Part-time/freelance/contract roles
  - Ambiguous or unverified experience
- Use strict date format: `MM/YYYY` (e.g., 04/2019)
- Calculate experience durations:
  - For current roles, use `{current_month_year}` as the end date
  - Account only for continuous work periods (ignore any gaps >3 months)
  - Do not overlap concurrent roles unless explicitly stated
- Output:
  - `total_professional_experience` = total full-time experience (in years, rounded to 1 decimal place)
  - `total_relevant_experience` = experience aligned to JD roles/responsibilities

3. Skills Assessment:
   - Match skills directly mentioned in resume
   - Verify context and practical application
   - No assumed or inferred skills

4. Education & Certifications:
   - List all formal degrees
   - Include only valid, relevant certifications
   - Verify certification status

### Phase 3: Scoring Criteria (0-100 scale)
- Skills Match: Relevance, depth, and recency
- Experience: Role alignment and impact
- Education: Degree relevance and prestige
- Certifications: Validity and relevance
- Location: Proximity or remote work alignment

### 1. **Score Calculation:**
- Total Score = Σ(Weight × Score for each criterion)
- Use {criteria_list} for weights.
- Maintain precision and fair variation. No copy-paste scoring across candidates.

### 2. **Tie-Breaking Order:**
- Apply this priority if multiple candidates have the same score: {priority_order}

### 3. **Good Resume Characteristics to Consider:
When evaluating resumes, give higher scores to those that include:
{good_resume_characteristics}

<｜begin▁of▁sentence｜>Job Description<｜end▁of▁sentence｜>
{job_desc}

<｜begin▁of▁sentence｜>Resume Content<｜end▁of▁sentence｜>
{resume}


<｜begin▁of▁sentence｜>Output Requirements<｜end▁of▁sentence｜>
Return JSON format:
{{
    "information": {{
        "name": "Full Name",
        "total_professional_experience": 7.0,
        "total_relevant_experience": 5.5,
        "skills": ["Python", "SQL"],
        "education": ["BSc Computer Science"],
        "certifications": ["AWS Certified"],
        "location": "City, State",
        "email": "email@example.com",
        "phone": "+1234567890"
    }},
    "evaluation": {{
        "skills_match": 85.75,
        "experience": 90.25,
        "education": 80.50,
        "certifications": 75.25,
        "location": 100.00,
        "total_score": 85.75,
        "explanation": "Detailed match analysis with specific differentiators..."
    }}
}}
"""
GOOD_RESUME_TEMPLATE = """You are an expert HR analyst examining resumes that were highly successful for a particular position.
        
I've provided you with resumes that were ranked as "good" matches for a job description.
Analyze these successful resumes and identify specific patterns, characteristics, or elements 
that made them effective.

The job description is:
{job_description}

Focus on patterns related to:
1. Content organization and structure
2. Skills presentation
3. Experience description style
4. Quantification of achievements
5. Relevance to job requirements
6. Education and certification presentation
7. Overall formatting and readability

Your output should be formatted exactly as:

"A good resume must include:
- [Concise point 1]
- [Concise point 2]
- [Concise point 3]
... and so on"

Keep each point brief, direct, and actionable. Do not add explanations or justifications.

Resume data:
{resumes_text}
"""
