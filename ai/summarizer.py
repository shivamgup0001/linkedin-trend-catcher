from openai import OpenAI
from google import genai
import os
from dotenv import load_dotenv

load_dotenv()

class Summarizer:
    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    def generate(self,prompt):

        response = self.client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
        )

        return response.text