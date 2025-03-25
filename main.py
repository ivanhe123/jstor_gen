import streamlit as st
import requests
import json
st.set_page_config(
    page_title="JSTOR Query Generator",
    page_icon="🔍",  # You can use an emoji or a local image file path.
    layout="centered"  # Optional: set layout (centered or wide)
)
# Function that calls the API to generate the AI's response given the conversation history.
def generate(history):
    response = requests.post(
        url="https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": "Bearer "+st.secrets["API"],
        },
        data=json.dumps({
            "model": "google/gemini-2.0-pro-exp-02-05:free",  # Replace with your chosen model.
            "messages": history
        })
    )
    #st.write(st.secrets["API"])
    res = response.json()["choices"][0]["message"]
    history.append({
        "role": res["role"],
        "content": res["content"]
    })
    return history

# Function that updates the conversation history with a new user message.
def newMsgToHistory(msg, img, history):
    history.append({
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": msg
            }
        ]
    })
    return history

# A helper function to display the chat history while skipping system messages.
def display_history(history):
    for message in history:
        # Skip displaying the engineered system prompt.
        if message["role"] == "system":
            continue
        role = message["role"]
        if isinstance(message["content"], list):
            text = " ".join(item.get("text", "") for item in message["content"])
        else:
            text = message["content"]
        text=text.replace(normal,"")
        st.chat_message(role).write(text)

# Function to initialize/reinitialize the conversation history with the engineered prompt.
def initialize_history():
    return [{
        "role": "system",
        "content": (
            normal
        )
    }]

normal = "You are an AI search query generator designed to convert natural language research requests into JSTOR advanced search queries. Your goal is to extract key subjects (such as titles, topics, author names, or historical influences) and to produce precise queries using field-specific terms and Boolean operators. For example, given the request 'I want to see any historical influences that influenced the writing of Fahrenheit 451 by Bradbury', the output should be: ((Fahrenheit 451) AND (Bradbury)) AND ((historical influence) OR (historical context) OR (historical factors)). Use <query></query> tags to indicate the final query. Place the final query after all the explanations. "
def main():
    st.header("JSTOR Advanced Search Query Generator")

    # Initialize session state variables if they don't exist.
    if "history" not in st.session_state:
        st.session_state.history = initialize_history()
    if "latest_explanation" not in st.session_state:
        st.session_state.latest_explanation = ""
    if "final_query" not in st.session_state:
        st.session_state.final_query = ""

    # Clear chat history button.
    if st.button("Clear Chat History"):
        st.session_state.history = initialize_history()
        st.session_state.latest_explanation = ""
        st.session_state.final_query = ""
        st.rerun()

    # Display chat history (skipping the system prompt).
    display_history(st.session_state.history)

    # Get new user message.
    user_input = st.chat_input("I want to research about...")
    if user_input:
        # Prepend a reminder prompt for context and append user input.
        custom_prompt = (
            normal+user_input
        )
        st.session_state.history = newMsgToHistory(custom_prompt, None, st.session_state.history)
        st.chat_message("user").write(user_input)

        # Generate the AI's response.
        with st.spinner("Generating response..."):
            st.session_state.history = generate(st.session_state.history)

        # Retrieve assistant's latest response.
        last_message = st.session_state.history[-1]
        if isinstance(last_message["content"], list):
            response_text = " ".join(item.get("text", "") for item in last_message["content"])
        else:
            response_text = last_message["content"]

        # Extract explanation and final query using the <query> tags.
        start_index = response_text.find("<query>")
        end_index = response_text.find("</query>")
        if start_index != -1 and end_index != -1:
            explanation = response_text[:start_index].strip()
            final_query = response_text[start_index + len("<query>"):end_index].strip()
        else:
            explanation = response_text.strip()
            final_query = ""

        # Save explanation and query in session state for persistence.
        st.session_state.latest_explanation = explanation
        st.session_state.final_query = final_query

    # Display explanation persistently below chat history.
    if st.session_state.latest_explanation:
        with st.expander("View Explanation"):
            st.write(st.session_state.latest_explanation)

    # Display the final query using st.code (which includes a built-in copy button).
    if st.session_state.final_query:
        st.markdown("**Final Query:**")
        st.code(st.session_state.final_query, language="text")

if __name__ == "__main__":
    main()
