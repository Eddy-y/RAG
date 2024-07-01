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
#thread_id = "thread_8qwOJFgPeTaMGJzCod59YIPS"
assis_id = "asst_sD5Wb80TKN5AW48tRI4q5cZk"
vector_store_id = "vs_qdWgRbQBBtmrJjGI1uO70opj"


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

if "attachment_list" not in st.session_state:
    st.session_state.attachment_list = []

#Set up our frontend page
st.set_page_config(
    page_title="Prove of Concept",
    page_icon=":books:"
)

# === FUNCTION DEFINITIONS =====

def upload_to_thread(file_path):
    with open(file_path, "rb") as file:
        response = client.files.create(file=file, purpose="assistants")
    return response.id

def upload_to_assistant():
    print("Paths: ", st.session_state.file_path_list)
    file_streams = [open(path, "rb") for path in st.session_state.file_path_list]
    try:
        file_batch = client.beta.vector_stores.file_batches.upload_and_poll(
            vector_store_id=vector_store_id, files=file_streams
        )
    finally:
        for stream in file_streams:
            stream.close()
        st.session_state.file_path_list = []

def delete_file_from_assistant(file_id):
    
    client.files.delete(file_id=file_id)
    # client.beta.assistants.files.delete(
    #     assistant_id=assis_id,
    #     file_id=file_id
    # )
    st.session_state.attachment_list = [
        attachment for attachment in st.session_state.attachment_list if attachment["file_id"] != file_id
    ]
    print("lista ids file: ", st.session_state.attachment_list)
    if st.session_state.attachment_list == []:
        st.session_state.start_chat = False  
  


# ==== Sidebar to upload files =======
file_uploaded = st.sidebar.file_uploader(
    "Upload a file to transform into embeddings",
    key="file_upoad"
)

#Upload file button (store file id)
if st.sidebar.button("Upload File to assistant VS"):
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
        #st.sidebar.write(f"File Name: {file_name}")

#Display file ids
if st.session_state.file_name_list:
    st.sidebar.write("Uploaded File IDs")
    for file_name in st.session_state.file_name_list:
        st.sidebar.write(file_name)
        # Upload files to OpenAI if there are files in the list
    if st.session_state.file_path_list:
        try:
            upload_to_assistant()
        except Exception as e:
            st.sidebar.error(f"Failed to upload files: {e}")

additional_files = st.sidebar.file_uploader(
            "Upload a file to add to the prompt",
            key="file_upload_prompt",
            type="pdf", 
            accept_multiple_files=True
        )   


# Button to iniciate the chat session
if st.sidebar.button("Start Chatting..."):
    #if st.session_state.file_name_list:

    if additional_files:
        attachment_list = []
        for additional_file in additional_files:
            # Get the file extension
            file_extension = os.path.splitext(additional_file.name)[1]

            # Create a temporary file with the same extension
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
                temp_file.write(additional_file.getbuffer())
                file_path = temp_file.name

            # Upload the file to OpenAI and get the file ID
            file_id = upload_to_thread(file_path)
            print(file_id)
            attachment_list.append({"file_id": file_id, "tools": [{"type": "file_search"}]})

        st.session_state.attachment_list.extend(attachment_list)
        st.session_state.start_chat = True

        #Create new thread for this chat session
        chat_thread = client.beta.threads.create(
            messages=[
                {
                "role": "user",
                # Attach the new file to the message.
                "content": "Genera le estimacion para el documento BAN?",
                "attachments": [
                    { "file_id": file_id, "tools": [{"type": "file_search"}] }
                ],
                }
            ]
        )
        st.session_state.thread_id = chat_thread.id
        # The thread now has a vector store with that file in its tool resources.
        print(chat_thread.tool_resources.file_search)
    else:
        st.sidebar.warning(
            "No files found, please upload atleast one file to get started"
        )

# Display uploaded files and provide a delete button for each
if 'attachment_list' in st.session_state:
    for attachment in st.session_state.attachment_list:
        file_id = attachment['file_id']
        st.write(f"File ID: {file_id}")
        if st.button(f"Delete {file_id}", key=f"delete_{file_id}"):
            delete_file_from_assistant(file_id)
            st.experimental_rerun()
 

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
            # Safely get the quote attribute, defaulting to a placeholder if it doesn't exist
            citation_quote = getattr(file_citation, "quote", "No quote available")
            # Append the formatted citation to the list
            citations.append(
                f'[{index + 1}] {citation_quote} from {cited_file["filename"]}'
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
st.title("First Prove of Concept")
st.write("Thread ID: ", st.session_state.thread_id)

# Chat interface
if st.session_state.start_chat:
    if "openai_model" not in st.session_state:
        st.session_state.openai_model = "gpt-4o"
    if "messages" not in st.session_state:
        st.session_state.messages = []


    # Show existing messages if any
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    #Chat input for the user
    if st.session_state.attachment_list != []:
        if prompt := st.chat_input("Whats new?"):
            #Add user message to the state and display
            st.session_state.messages.append({"role":"user", "content":prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            print("Attachments: ", st.session_state.attachment_list)
            # Add the user message to the existing thread
            client.beta.threads.messages.create(
                thread_id=st.session_state.thread_id,
                role="user",
                content=prompt,
                attachments=st.session_state.attachment_list
            )
            st.session_state.attachment_list = []

            # Create a run with additional instructions
            run = client.beta.threads.runs.create(
                thread_id=st.session_state.thread_id,
                assistant_id=assis_id
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

                # Process and display assistant messages
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
    else: 
        # Promopt users to start chat
        st.write(
            "Please upload at least a file to get started by clicking on the 'Start Chat' button"
        )

