import streamlit as st
from openai import OpenAI
import json
import random
import PyPDF2
import docx
import re
import base64
from io import BytesIO
from PIL import Image

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
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image}",
                            "detail": "low"  # Always use low detail for images
                        }
                    }
                ]
            }
        ]
        model = "gpt-4o" 
    else:
        messages = [
            {"role": "system", "content": "You are specialized in generating Q&A in specific formats according to the instructions of the user. The questions are used in a vocational school in switzerland. if the user itself upload a test with Q&A, then you transform the original test into the specified formats."},
            {"role": "user", "content": prompt}
        ]
        model = "gpt-4o"  # Using GPT-4o for text-only tasks

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=300
    )
    return response.choices[0].message.content

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
        text += page.extract_text()
    return text

def extract_text_from_docx(file):
    doc = docx.Document(file)
    text = ""
    for paragraph in doc.paragraphs:
        text += paragraph.text + "\n"
    return text

def main():
    st.title("OLAT Fragen Generator")

    # File upload option
    uploaded_file = st.file_uploader("Upload a PDF, DOCX, or image file", type=["pdf", "docx", "jpg", "jpeg", "png"])

    # Image paste option
    pasted_image = st.image_input("Or paste an image here:")

    text_content = ""
    image_content = None

    if uploaded_file is not None:
        if uploaded_file.type in ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]:
            if uploaded_file.type == "application/pdf":
                text_content = extract_text_from_pdf(uploaded_file)
            else:
                text_content = extract_text_from_docx(uploaded_file)
            st.success("Text extracted successfully. You can now edit it in the text area below.")
        elif uploaded_file.type.startswith('image/'):
            image_bytes = uploaded_file.getvalue()
            image_content = base64.b64encode(image_bytes).decode('utf-8')
            st.image(uploaded_file, caption='Uploaded Image', use_column_width=True)
            st.success("Image uploaded successfully. You can now ask questions about the image.")
        else:
            st.error("Unsupported file type. Please upload a PDF, DOCX, or image file.")
    elif pasted_image is not None:
        # Convert pasted image to base64
        buffered = BytesIO()
        pasted_image.save(buffered, format="PNG")
        image_content = base64.b64encode(buffered.getvalue()).decode('utf-8')
        st.success("Image pasted successfully. You can now ask questions about the image.")

    user_input = st.text_area("Enter your text or question about the image:", value=text_content)
    learning_goals = st.text_area("Learning Goals (Optional):")

    selected_types = st.multiselect("Select question types to generate:", MESSAGE_TYPES)

    if st.button("Generate Questions"):
        if (user_input or image_content) and selected_types:
            all_responses = ""
            generated_content = {}
            for msg_type in selected_types:
                prompt_template = read_prompt_from_md(msg_type)
                full_prompt = f"{prompt_template}\n\nUser Input: {user_input}\n\nLearning Goals: {learning_goals}"
                
                try:
                    response = get_chatgpt_response(full_prompt, image_content)
                    
                    if msg_type == "inline_fib":
                        processed_response = transform_output(response)
                        generated_content[f"{msg_type.replace('_', ' ').title()} (Processed)"] = processed_response
                        all_responses += f"{processed_response}\n\n"
                    else:
                        generated_content[msg_type.replace('_', ' ').title()] = response
                        all_responses += f"{response}\n\n"
                except Exception as e:
                    st.error(f"An error occurred for {msg_type}: {str(e)}")
            
            # Display titles of generated content with checkmarks
            st.subheader("Generated Content:")
            for title in generated_content.keys():
                st.write(f"✔ {title}")
            
            if all_responses:
                st.download_button(
                    label="Download All Responses",
                    data=all_responses,
                    file_name="all_responses.txt",
                    mime="text/plain"
                )
        elif not user_input and not image_content:
            st.warning("Please enter some text, upload a file, or paste an image.")
        elif not selected_types:
            st.warning("Please select at least one question type.")

if __name__ == "__main__":
    main()
