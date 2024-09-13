import streamlit as st
from openai import OpenAI
import json
import random
import PyPDF2
import docx
import re
import base64
from pdf2image import convert_from_bytes  # New import
import io

# Access API key from Streamlit secrets
OPENAI_API_KEY = st.secrets["openai"]["api_key"]
client = OpenAI(api_key=OPENAI_API_KEY)

# List of available message types
MESSAGE_TYPES = [
    "single_choice",
    "multiple_choice",
    "kprim",
    "truefalse",
    "draganddrop",
    "inline_fib"
]

def read_prompt_from_md(filename):
    with open(f"{filename}.md", "r") as file:
        return file.read()

def get_chatgpt_response(prompt, image=None):
    if image:
        # Convert image to base64
        image_base64 = base64.b64encode(image.getvalue()).decode('utf-8')
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": f"data:image/jpeg;base64,{image_base64}"}
                ]
            }
        ]
        model = "gpt-4-vision-preview"

    else:
        messages = [
            {"role": "system", "content": "You are specialized in generating Q&A in specific formats according to the instructions of the user. The questions are used in a vocational school in Switzerland. If the user uploads a test with Q&A, then you transform the original test into the specified formats."},
            {"role": "user", "content": prompt}
        ]
        model = "gpt-4o"
    
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=4000
    )
    return response.choices[0].message.content

def process_images(images):
    for idx, image in enumerate(images):
        st.image(image, caption=f'Page {idx+1}', use_column_width=True)
        user_input = st.text_area(f"Enter your question or instructions for Page {idx+1}:", key=f"text_area_{idx}")
        learning_goals = st.text_area(f"Learning Goals for Page {idx+1} (Optional):", key=f"learning_goals_{idx}")
        selected_types = st.multiselect(f"Select question types for Page {idx+1}:", MESSAGE_TYPES, key=f"selected_types_{idx}")
        if st.button(f"Generate Questions for Page {idx+1}", key=f"generate_button_{idx}"):
            if user_input and selected_types:
                generate_questions_with_image(user_input, learning_goals, selected_types, image)
            else:
                st.warning(f"Please enter text and select question types for Page {idx+1}.")

def generate_questions_with_image(user_input, learning_goals, selected_types, image):
    all_responses = ""
    generated_content = {}
    for msg_type in selected_types:
        prompt_template = read_prompt_from_md(msg_type)
        full_prompt = f"{prompt_template}\n\nUser Input: {user_input}\n\nLearning Goals: {learning_goals}"
        try:
            response = get_chatgpt_response(full_prompt, image=image)
            if msg_type == "inline_fib":
                processed_response = transform_output(response)
                generated_content[f"{msg_type.replace('_', ' ').title()} (Processed)"] = processed_response
                all_responses += f"{processed_response}\n\n"
            else:
                generated_content[msg_type.replace('_', ' ').title()] = response
                all_responses += f"{response}\n\n"
        except Exception as e:
            st.error(f"An error occurred for {msg_type}: {str(e)}")
    st.subheader("Generated Content:")
    for title, content in generated_content.items():
        st.markdown(f"### {title}")
        st.code(content)

def clean_json_string(s):
    s = s.strip()
    s = re.sub(r'^```json\s*', '', s)
    s = re.sub(r'\s*```$', '', s)
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r'(?<=text": ")(.+?)(?=")', lambda m: m.group(1).replace('\n', '\\n'), s)
    s = ''.join(char for char in s if ord(char) >= 32 or char == '\n')
    match = re.search(r'\[.*\]', s, re.DOTALL)
    return match.group(0) if match else s

def convert_json_to_text_format(json_input):
    if isinstance(json_input, str):
        data = json.loads(json_input)
    else:
        data = json_input

    fib_output = []
    ic_output = []

    for item in data:
        text = item.get('text', '')
        blanks = item.get('blanks', [])
        wrong_substitutes = item.get('wrong_substitutes', [])

        num_blanks = len(blanks)

        fib_lines = [
            "Type\tFIB",
            "Title\t✏✏Vervollständigen Sie die Lücken mit dem korrekten Begriff.✏✏",
            f"Points\t{num_blanks}"
        ]

        for blank in blanks:
            text = text.replace(blank, "{blank}", 1)

        parts = text.split("{blank}")
        for index, part in enumerate(parts):
            fib_lines.append(f"Text\t{part.strip()}")
            if index < len(blanks):
                fib_lines.append(f"1\t{blanks[index]}\t20")

        fib_output.append('\n'.join(fib_lines))

        ic_lines = [
            "Type\tInlinechoice",
            "Title\tWörter einordnen",
            "Question\t✏✏Wählen Sie die richtigen Wörter.✏✏",
            f"Points\t{num_blanks}"
        ]

        all_options = blanks + wrong_substitutes
        random.shuffle(all_options)

        for index, part in enumerate(parts):
            ic_lines.append(f"Text\t{part.strip()}")
            if index < len(blanks):
                options_str = '|'.join(all_options)
                ic_lines.append(f"1\t{options_str}\t{blanks[index]}\t|")

        ic_output.append('\n'.join(ic_lines))

    return '\n\n'.join(fib_output), '\n\n'.join(ic_output)

def transform_output(json_string):
    try:
        cleaned_json_string = clean_json_string(json_string)
        json_data = json.loads(cleaned_json_string)
        fib_output, ic_output = convert_json_to_text_format(json_data)
        return f"{ic_output}\n---\n{fib_output}"
    except json.JSONDecodeError as e:
        st.error(f"Error parsing JSON: {e}")
        st.text("Cleaned input:")
        st.code(cleaned_json_string, language='json')
        st.text("Original input:")
        st.code(json_string)
        
        try:
            if not cleaned_json_string.strip().endswith(']'):
                cleaned_json_string += ']'
            partial_json = json.loads(cleaned_json_string)
            st.warning("Attempted to salvage partial JSON. Results may be incomplete.")
            fib_output, ic_output = convert_json_to_text_format(partial_json)
            return f"{ic_output}\n---\n{fib_output}"
        except:
            st.error("Unable to salvage partial JSON.")
            return "Error: Invalid JSON format"
    except Exception as e:
        st.error(f"Error processing input: {str(e)}")
        st.text("Original input:")
        st.code(json_string)
        return "Error: Unable to process input"

def extract_text_from_pdf(file):
    pdf_reader = PyPDF2.PdfReader(file)
    text = ""
    for page in pdf_reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text
    return text.strip()

def is_pdf_ocr(text):
    if not text:
        return False
    alphanumeric_chars = sum(c.isalnum() for c in text)
    total_chars = len(text)
    if total_chars == 0:
        return False
    ratio = alphanumeric_chars / total_chars
    return ratio > 0.1

def convert_pdf_to_images(file):
    images = convert_from_bytes(file.read())
    image_buffers = []
    for img in images:
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        image_buffers.append(img_buffer)
    return image_buffers


def extract_text_from_docx(file):
    doc = docx.Document(file)
    text = ""
    for paragraph in doc.paragraphs:
        text += paragraph.text + "\n"
    return text

def main():
    st.title("OLAT Fragen Generator")

    uploaded_file = st.file_uploader("Upload a PDF, DOCX, or image file", type=["pdf", "docx", "jpg", "jpeg", "png"])

    if uploaded_file is not None:
        if uploaded_file.type == "application/pdf":
            # Extract text from the PDF
            text_content = extract_text_from_pdf(uploaded_file)
            # Reset the file pointer to the beginning
            uploaded_file.seek(0)
            # Check if the PDF is OCRed
            if is_pdf_ocr(text_content):
                st.success("Text extracted successfully. Processing with GPT-4o.")
                process_text_input(text_content)
            else:
                st.warning("No extractable text found. Converting PDF pages to images for GPT-4o Vision.")
                images = convert_pdf_to_images(uploaded_file)
                process_images(images)
        elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            text_content = extract_text_from_docx(uploaded_file)
            st.success("Text extracted successfully from DOCX. Processing with GPT-4o.")
            process_text_input(text_content)
        elif uploaded_file.type.startswith('image/'):
            image_bytes = uploaded_file.getvalue()
            st.image(uploaded_file, caption='Uploaded Image', use_column_width=True)
            st.success("Image uploaded successfully. Processing with GPT-4 Vision.")
            process_images([io.BytesIO(image_bytes)])
        else:
            st.error("Unsupported file type. Please upload a PDF, DOCX, or image file.")
    else:
        st.info("Please upload a file to proceed.")

def process_text_input(text_content):
    user_input = st.text_area("Enter your text or question:", value=text_content)
    learning_goals = st.text_area("Learning Goals (Optional):")
    selected_types = st.multiselect("Select question types to generate:", MESSAGE_TYPES)
    if st.button("Generate Questions"):
        if user_input and selected_types:
            generate_questions(user_input, learning_goals, selected_types)
        else:
            st.warning("Please enter some text and select at least one question type.")

def process_images(images):
    for idx, image in enumerate(images):
        st.image(image, caption=f'Page {idx+1}', use_column_width=True)
        user_input = st.text_area(f"Enter your question or instructions for Page {idx+1}:", key=f"text_area_{idx}")
        learning_goals = st.text_area(f"Learning Goals for Page {idx+1} (Optional):", key=f"learning_goals_{idx}")
        selected_types = st.multiselect(f"Select question types for Page {idx+1}:", MESSAGE_TYPES, key=f"selected_types_{idx}")
        if st.button(f"Generate Questions for Page {idx+1}", key=f"generate_button_{idx}"):
            if user_input and selected_types:
                generate_questions_with_image(user_input, learning_goals, selected_types, image)
            else:
                st.warning(f"Please enter text and select question types for Page {idx+1}.")

def generate_questions(user_input, learning_goals, selected_types):
    all_responses = ""
    generated_content = {}
    for msg_type in selected_types:
        prompt_template = read_prompt_from_md(msg_type)
        full_prompt = f"{prompt_template}\n\nUser Input: {user_input}\n\nLearning Goals: {learning_goals}"
        try:
            response = get_chatgpt_response(full_prompt)
            if msg_type == "inline_fib":
                processed_response = transform_output(response)
                generated_content[f"{msg_type.replace('_', ' ').title()} (Processed)"] = processed_response
                all_responses += f"{processed_response}\n\n"
            else:
                generated_content[msg_type.replace('_', ' ').title()] = response
                all_responses += f"{response}\n\n"
        except Exception as e:
            st.error(f"An error occurred for {msg_type}: {str(e)}")
    st.subheader("Generated Content:")
    for title, content in generated_content.items():
        st.markdown(f"### {title}")
        st.code(content)

def generate_questions_with_image(user_input, learning_goals, selected_types, image):
    all_responses = ""
    generated_content = {}
    for msg_type in selected_types:
        prompt_template = read_prompt_from_md(msg_type)
        full_prompt = f"{prompt_template}\n\nUser Input: {user_input}\n\nLearning Goals: {learning_goals}"
        try:
            image_bytes = image.getvalue()
            response = get_chatgpt_response(full_prompt, image=image_bytes)
            if msg_type == "inline_fib":
                processed_response = transform_output(response)
                generated_content[f"{msg_type.replace('_', ' ').title()} (Processed)"] = processed_response
                all_responses += f"{processed_response}\n\n"
            else:
                generated_content[msg_type.replace('_', ' ').title()] = response
                all_responses += f"{response}\n\n"
        except Exception as e:
            st.error(f"An error occurred for {msg_type}: {str(e)}")
    st.subheader("Generated Content:")
    for title, content in generated_content.items():
        st.markdown(f"### {title}")
        st.code(content)

def get_chatgpt_response(prompt, image=None):
    if image:
        messages = [
            {
                "role": "user",
                "content": prompt,
                "image": image  # Include the image in the message
            }
        ]
        model = "gpt-4-vision"
    else:
        messages = [
            {"role": "system", "content": "You are specialized in generating Q&A in specific formats according to the instructions of the user. The questions are used in a vocational school in Switzerland. If the user uploads a test with Q&A, then you transform the original test into the specified formats."},
            {"role": "user", "content": prompt}
        ]
        model = "gpt-4o"
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=1000
    )
    return response.choices[0].message.content

if __name__ == "__main__":
    main()
