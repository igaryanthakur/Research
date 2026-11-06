import os
from dotenv import load_dotenv
load_dotenv()
from google import genai
client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY'))
response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents='Respond with 200 OK if you can read this.'
)
print("Gemini Response:", response.text)
