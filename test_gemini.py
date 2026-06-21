from google import genai
from django.conf import settings

# Initialize the client using the modern SDK layout
client = genai.Client(api_key=settings.GEMINI_API_KEY)
# Call the correct method with a fully supported model
response = client.models.generate_content(
    model='gemini-2.5-flash-lite',
    contents='Say hello',
)

print(response.text)