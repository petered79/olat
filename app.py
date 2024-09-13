import streamlit as st
import openai  # Corrected the import
import json
import random
import PyPDF2
import docx
import re
import base64
from pdf2image import convert_from_bytes
import io
from PIL import Image
import logging

# Set up logging for better error tracking
logging.basicConfig(level=logging.INFO)

# Access API key from Streamlit secrets
openai.api_key = st.secrets["openai"]["api_key"]

# List of available message types
MESSAGE_TYPES = [
    "single_choice",
    "multiple_choice",
    "kprim",
    "truefalse",
    "draganddrop",
    "inline_fib"
]

@st.cache_data
def read_prompt_from_md(filename):
    """Read the prompt from a markdown file and cache the result."""
    with open(f"{filename}.md", "r") as file:
        return file.read()

@st.cache_data
def process_image(image):
    """Process and resize an image to reduce memory footprint."""
    if isinstance(image, (str, bytes)):
        img = Image.open(io.BytesIO(base64.b64decode(image) if isinstance(image, str) else image))
    elif isinstance(image, Image.Image):
        img = image
    else:
        img = Image.open(image)

    # Convert to RGB mode if it's not
    if img.mode != 'RGB':
        img = img.convert('RGB')

    # Resize if the image is too large
    max_size = 1000  # Reduced max size to reduce memory consumption
    if max(img.size) > max_size:
        img.thumbnail((max_size, max_size))

    # Save to bytes
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG')
    img_byte_arr = img_byte_arr.getvalue()

    return base64.b64encode(img_byte_arr).decode('utf-8')

def get_chatgpt_response(prompt, image=None):
    """Fetch response from OpenAI GPT with error handling."""
    try:
        if image:
            base64_image = process_image(image)
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                                "detail": "low"
                            }
                        }
                    ]
                }
            ]
        else:
            messages = [
                {"role": "system", "content": "You are specialized in generating Q&A in specific formats..."},
                {"role": "user", "content": prompt}
            ]

        response = openai.ChatCompletion.create(
            model="gpt-4o",  # Corrected to match actual OpenAI model name
            messages=messages,
            max_tokens=4000
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"Error communicating with OpenAI API: {e}")
        logging.error(f"Error communicating with OpenAI API: {e}")
        return None

def process_images(images):
    """Process uploaded images and generate questions."""
    for idx, image in enumerate(images):
        st.image(image, caption=f'Page {idx+1}', use_column_width=True)

        # Text area for user input and learning goals
        user_input = st.text_area(f"Enter your question or instructions for Page {idx+1}:", key=f"text_area_{idx}")
        learning_goals = st.text_area(f"Learning Goals for Page {idx+1} (Optional):", key=f"learning_goals_{idx}")
        selected_types = st.multiselect(f"Select question types for Page {idx+1}:", MESSAGE_TYPES, key=f"selected_types_{idx}")

        # Use session state to track the button click status
        generate_key = f"generate_button_{idx}"
        if generate_key not in st.session_state:
            st.session_state[generate_key] = False

        # Button to generate questions for the page
        if st.button(f"Generate Questions for Page {idx}", key=generate_key):
            st.session_state[generate_key] = True

        # Generate questions if the button is clicked
        if st.session_state[generate_key]:
            if user_input and selected_types:
                generate_questions_with_image(user_input, learning_goals, selected_types, image)
            else:
                st.warning(f"Please enter text and select question types for Page {idx+1}.")



def generate_questions_with_image(user_input, learning_goals, selected_types, image):
    """Generate questions for the image and handle errors."""
    all_responses = ""
    generated_content = {}
    for msg_type in selected_types:
        prompt_template = read_prompt_from_md(msg_type)
        full_prompt = f"{prompt_template}\n\nUser Input: {user_input}\n\nLearning Goals: {learning_goals}"
        try:
            response = get_chatgpt_response(full_prompt, image=image)
            if response:
                if msg_type == "inline_fib":
                    processed_response = transform_output(response)
                    generated_content[f"{msg_type.replace('_', ' ').title()} (Processed)"] = processed_response
                    all_responses += f"{processed_response}\n\n"
                else:
                    generated_content[msg_type.replace('_', ' ').title()] = response
                    all_responses += f"{response}\n\n"
            else:
                st.error(f"Failed to generate a response for {msg_type}.")
        except Exception as e:
            st.error(f"An error occurred for {msg_type}: {str(e)}")

    # Display generated content with checkmarks
    st.subheader("Generated Content:")
    for title in generated_content.keys():
        st.write(f"✔ {title}")

    # Download button for all responses
    if all_responses:
        st.download_button(
            label="Download All Responses",
            data=all_responses,
            file_name="all_responses.txt",
            mime="text/plain"
        )

@st.cache_data
def convert_pdf_to_images(file):
    """Convert PDF pages to images."""
    images = convert_from_bytes(file.read())
    return images

@st.cache_data
def extract_text_from_pdf(file):
    """Extract text from PDF using PyPDF2."""
    pdf_reader = PyPDF2.PdfReader(file)
    text = ""
    for page in pdf_reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text
    return text.strip()

@st.cache_data
def extract_text_from_docx(file):
    """Extract text from DOCX file."""
    doc = docx.Document(file)
    text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
    return text.strip()

def process_pdf(file):
    text_content = extract_text_from_pdf(file)
    
    # If no text is found, assume it's a non-OCR PDF
    if not text_content or not is_pdf_ocr(text_content):
        st.warning("This PDF is not OCRed. Text extraction failed. Please upload an OCRed PDF.")
        return None, convert_pdf_to_images(file)  # Fallback to image processing
    else:
        return text_content, None


def main():
    """Main function for the Streamlit app."""
    st.title("OLAT Fragen Generator")

    uploaded_file = st.file_uploader("Upload a PDF, DOCX, or image file", type=["pdf", "docx", "jpg", "jpeg", "png"])

    text_content = ""
    image_content = None
    images = []

    if uploaded_file is not None:
        if uploaded_file.type == "application/pdf":
            text_content = extract_text_from_pdf(uploaded_file)
            if text_content:
                st.success("Text extracted from PDF. You can now edit it in the text area below.")
            else:
                images = convert_pdf_to_images(uploaded_file)
                st.success("PDF converted to images. You can now ask questions about each page.")
        elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            text_content = extract_text_from_docx(uploaded_file)
            st.success("Text extracted successfully. You can now edit it in the text area below.")
        elif uploaded_file.type.startswith('image/'):
            image_content = Image.open(uploaded_file)
            st.image(image_content, caption='Uploaded Image', use_column_width=True)
            st.success("Image uploaded successfully. You can now ask questions about the image.")
        else:
            st.error("Unsupported file type. Please upload a PDF, DOCX, or image file.")

    if images:
        process_images(images)
    else:
        user_input = st.text_area("Enter your text or question about the image:", value=text_content)
        learning_goals = st.text_area("Learning Goals (Optional):")
        selected_types = st.multiselect("Select question types to generate:", MESSAGE_TYPES)

        if st.button("Generate Questions"):
            if user_input or image_content and selected_types:
                generate_questions_with_image(user_input, learning_goals, selected_types, image_content)
            elif not user_input and not image_content:
                st.warning("Please enter some text, upload a file, or upload an image.")
            elif not selected_types:
                st.warning("Please select at least one question type.")

if __name__ == "__main__":
    main()
