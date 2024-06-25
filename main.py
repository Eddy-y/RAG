import os
from dotenv import load_dotenv
import openai
import requests
import json
import tempfile

import time
import logging
from datetime import datetime
import streamlit as st


load_dotenv()

client = openai.OpenAI()

model = "gpt-3.5-turbo" #"gpt-4-1106-preview"

# == Hardcoded ids to be used once the first code run is done and the assistant was created
thread_id = "thread_H5lFYbfk7pPPWlCZNEpJxWRg"
assis_id = "asst_5iPIvOvOI4Aa9LhWPQqurnie"
vector_store_id = "vs_5FdWLMeipOsyTn97Du7Xi07p"


#Initialize all the sessions
if "file_path_list" not in st.session_state:
    st.session_state.file_path_list=[]

if 'file_name_list' not in st.session_state:
    st.session_state.file_name_list = []

if "start_chat" not in st.session_state:
    st.session_state.start_chat = False

if "thread_id" not in st.session_state:
    st.session_state.thread_id = None

if "vector_store_id" not in st.session_state:
    st.session_state.vector_store_id = None

#Set up our frontend page
st.set_page_config(
    page_title="Study Buddy",
    page_icon=":books:"
)

# === FUNCTION DEFINITIONS =====

# def upload_to_openai(filepath):
#     with open(filepath, "rb") as file:
#         response = client.files.create(file=file.read(), purpose="assistants")
#     return response.id

def upload_to_openai2():
    print("Paths: ", st.session_state.file_path_list)
    file_streams = [open(path, "rb") for path in st.session_state.file_path_list]
    try:
        file_batch = client.beta.vector_stores.file_batches.upload_and_poll(
            vector_store_id=vector_store_id, files=file_streams
        )
    finally:
        for stream in file_streams:
            stream.close()


# ==== Sidebar to upload files =======
file_uploaded = st.sidebar.file_uploader(
    "Upload a file to transform into embeddings",
    key="file_upoad"
)

#Upload file button (store file id)
if st.sidebar.button("Upload File"):
    if file_uploaded:
        # Get the file extension
        file_extension = os.path.splitext(file_uploaded.name)[1]
        
        # Create a temporary file with the same extension
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
            temp_file.write(file_uploaded.getbuffer())
            file_path = temp_file.name
            file_name = file_uploaded.name

        # Append the file name and path to the session state lists
        st.session_state.file_name_list.append(file_name)
        st.session_state.file_path_list.append(file_path)
        # Display the uploaded file name in the sidebar
        st.sidebar.write(f"File Name: {file_name}")

#Display file ids
if st.session_state.file_name_list:
    st.sidebar.write("Uploaded File IDs")
    for file_name in st.session_state.file_name_list:
        st.sidebar.write(file_name)
        # Upload files to OpenAI if there are files in the list
    if st.session_state.file_path_list:
        try:
            upload_to_openai2()
        except Exception as e:
            st.sidebar.error(f"Failed to upload files: {e}")

# Button to iniciate the chat session
if st.sidebar.button("Start Chatting..."):
    if st.session_state.file_name_list:
        st.session_state.start_chat = True

        #Create new thread for this chat session
        chat_thread = client.beta.threads.create()
        st.session_state.thread_id = chat_thread.id
        st.write("Thread ID: ", chat_thread.id)
    else:
        st.sidebar.warning(
            "No files found, please upload atleast one file to get started"
        )

# Define the function to process messages with citations
def process_message_with_citations(message):
    """Extract content and annotations from the message and format citations as footnotes."""
    message_content = message.content[0].text
    annotations = (
        message_content.annotations if hasattr(message_content, "annotations") else []
    )
    citations = []

    # Iterate over the annotations and add footnotes
    for index, annotation in enumerate(annotations):
        # Replace the text with a footnote
        message_content.value = message_content.value.replace(
            annotation.text, f" [{index + 1}]"
        )

        # Gather citations based on annotation attributes
        if file_citation := getattr(annotation, "file_citation", None):
            # Retrieve the cited file details (dummy response here since we can't call OpenAI)
            cited_file = {
                "filename": "cryptocurrency.pdf"
            }  # This should be replaced with actual file retrieval
            citations.append(
                f'[{index + 1}] {file_citation.quote} from {cited_file["filename"]}'
            )
        elif file_path := getattr(annotation, "file_path", None):
            # Placeholder for file download citation
            cited_file = {
                "filename": "cryptocurrency.pdf"
            }  # TODO: This should be replaced with actual file retrieval
            citations.append(
                f'[{index + 1}] Click [here](#) to download {cited_file["filename"]}'
            )  # The download link should be replaced with the actual download path

    # Add footnotes to the end of the message content
    full_response = message_content.value + "\n\n" + "\n".join(citations)
    return full_response
 
 #The main interface
st.title("Study byddy")
st.write("Learn fast by chatting")

#Check sessions
if st.session_state.start_chat:
    if "openai_model" not in st.session_state:
        st.session_state.openai_model = "gpt-3.5-turbo"
    if "messages" not in st.session_state:
        st.session_state.messages = []
    #Show existing messages if any
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["contet"])
            
    #Char input for the user
    if prompt := st.chat_input("Whats new?"):
        #Add user message to the state and display
        st.session_state.messages.append({"role":"user", "content":prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        #Add the user message to the existing thread
        client.beta.threads.messages.create(
            thread_id=st.session_state.thread_id,
            role="user",
            content=prompt
        )

        # Create a run with additioal instructions
        run = client.beta.threads.runs.create(
            thread_id=st.session_state.thread_id,
            assistant_id=assis_id,
            instructions="""Please answer the questions using the knowledge provided in the files.
            when adding additional information, make sure to distinguish it with bold or underlined text.""",
        )

        # Show a spinner while the assistant is thinking...
        with st.spinner("Wait... Generating response..."):
            while run.status != "completed":
                time.sleep(1)
                run = client.beta.threads.runs.retrieve(
                    thread_id=st.session_state.thread_id, run_id=run.id
                )
            # Retrieve messages added by the assistant
            messages = client.beta.threads.messages.list(
                thread_id=st.session_state.thread_id
            )
            # Process and display assis messages
            assistant_messages_for_run = [
                message
                for message in messages
                if message.run_id == run.id and message.role == "assistant"
            ]

            for message in assistant_messages_for_run:
                full_response = process_message_with_citations(message=message)
                st.session_state.messages.append(
                    {"role": "assistant", "content": full_response}
                )
                with st.chat_message("assistant"):
                    st.markdown(full_response, unsafe_allow_html=True)

    else:
        # Promopt users to start chat
        st.write(
            "Please upload at least a file to get started by clicking on the 'Start Chat' button"
        )