from google import genai

# Initialize the client using the modern SDK layout


# Call the correct method with a fully supported model
response = client.models.generate_content(
    model='gemini-2.5-flash-lite',
    contents='Say hello',
)

print(response.text)