from google import genai

# Paste your Gemini API key here

import os

API_KEY = os.getenv("GEMINI_API_KEY")
# Create the client
client = genai.Client(api_key=API_KEY)

# Send a prompt
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Hello Gemini! Introduce yourself in 3 lines."
)

# Print the response
print("\nGemini Response:\n")
print(response.text)