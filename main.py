import streamlit as st
import requests
import json
import re # Import regular expressions
import urllib.parse # Import URL encoding

st.set_page_config(
    page_title="Advanced Academic Search Query Generator",
    page_icon="🔍",
    layout="wide" # Changed to wide for potentially longer lists of queries
)

# --- Platform Specific Prompts ---

# Define base instruction for generating multiple queries
MULTI_QUERY_INSTRUCTION = """
Generate {num_variations} distinct query variations based on the user's request below.
Use the specific syntax rules for {platform_name}.
Provide a brief general explanation first, then list the queries.
Enclose *each* generated query within its own <query>...</query> tags, with each tag pair on a new line.
Example for multiple queries:
Explanation text...
<query>Query 1 using {platform_name} syntax</query>
<query>Query 2 using {platform_name} syntax</query>
"""

# JSTOR Prompt
JSTOR_SYNTAX_RULES = """
You are an AI search query generator designed to convert natural language research requests into JSTOR advanced search queries.
Your goal is to extract key subjects and to produce precise queries using field-specific terms and Boolean operators (AND, OR, NOT).
- Use AND to combine distinct concepts (narrows results). Must be uppercase.
- Use OR within parentheses `()` to group synonyms or related terms (broadens results). Must be uppercase.
- Use NOT to exclude terms (narrows results). Must be uppercase.
- Surround key subjects or phrases with parentheses `()` for clarity and grouping, especially with OR. Do NOT use "" or ''.
- Example: ((Fahrenheit 451) AND (Bradbury)) AND ((historical influence) OR (historical context) OR (historical factors))
"""
JSTOR_SYSTEM_PROMPT = JSTOR_SYNTAX_RULES # Base prompt, instruction for multiple queries will be added dynamically

# Google Scholar Prompt
GOOGLE_SCHOLAR_SYNTAX_RULES = """
You are an AI search query generator designed to convert natural language research requests into Google Scholar search queries.
Your goal is to extract key subjects and to produce precise queries using Google Scholar's operators.
- Use `AND` (or just spaces between terms) to find results containing all terms (narrows). AND must be uppercase if used explicitly.
- Use `OR` to find results containing either term (broadens). OR must be uppercase. Group with parentheses `()` if needed. Example: library (anxiety OR fear)
- Use the minus sign `-` immediately before a term to exclude it (narrows). Do NOT spell out NOT. No space after hyphen. Example: library anxiety -graduate
- Use `AROUND(n)` between terms to find them within 'n' words of each other (narrows). Must be uppercase. Example: library AROUND(5) graduate
- Use double quotes `" "` around exact phrases. Example: "library anxiety"
- Use `intitle:` before a term to find it in the article title. No space after colon. Example: intitle:anxiety
- Use `author:` before an author's name (in quotes) to find articles by them. No space after colon. Example: author:"jane doe"
- Use `source:` before a journal title (in quotes) to find articles in that publication. No space after colon. Example: source:"nature communications"
- The hyphen `-` can also connect words strongly: `decision-making`. No spaces around hyphen.
"""
GOOGLE_SCHOLAR_SYSTEM_PROMPT = GOOGLE_SCHOLAR_SYNTAX_RULES # Base prompt, instruction for multiple queries will be added dynamically

# --- API Call Function ---
def generate(history):
    # Ensure the API key is available
    api_key = st.secrets.get("API")
    if not api_key:
        st.error("API key not found. Please configure secrets.")
        return None # Return None or raise an error

    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json" # Added Content-Type header
            },
            data=json.dumps({
                "model": "deepseek/deepseek-r1:free", # Switched to a known non-experimental model
                "messages": history,
                # Add other parameters like temperature if needed
                # "temperature": 0.7,
            })
        )
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        
        response_data = response.json()
        
        # Check if 'choices' is in the response and not empty
        if "choices" in response_data and response_data["choices"]:
            res = response_data["choices"][0]["message"]
            # Add assistant's response back to history
            history.append({
                "role": res.get("role", "assistant"), # Use .get for safety
                "content": res.get("content", "")
            })
            return history
        else:
            # Handle cases where response might be missing 'choices' (e.g., content filtering)
            st.error(f"API response did not contain expected data. Response: {response_data}")
            # Optionally remove the last user message from history if generation failed
            if history and history[-1]["role"] == "user":
                 history.pop()
            return history # Return history as it was before the failed attempt

    except requests.exceptions.RequestException as e:
        st.error(f"API request failed: {e}")
        # Optionally remove the last user message from history if generation failed
        if history and history[-1]["role"] == "user":
             history.pop()
        return history # Return history as it was before the failed attempt
    except json.JSONDecodeError:
        st.error(f"Failed to decode API response: {response.text}")
        if history and history[-1]["role"] == "user":
             history.pop()
        return history
    except Exception as e: # Catch any other unexpected errors
        st.error(f"An unexpected error occurred: {e}")
        if history and history[-1]["role"] == "user":
             history.pop()
        return history

# --- History Management ---
def newMsgToHistory(msg, history):
    # Simple append now, system prompt handled separately
    history.append({
        "role": "user",
        "content": msg # User message is just the text input now
    })
    return history

# A helper function to display the chat history, skipping system messages
def display_history(history):
    for message in history:
        if message["role"] == "system":
            continue
        role = message["role"]
        content = message["content"]
        # Simple display, assuming content is always text for now
        st.chat_message(role).write(content)

# Function to initialize/reinitialize the conversation history
# System prompt is NOT added here, it's added dynamically before API call
def initialize_history():
    return [] # Start with an empty history

# --- Main App Logic ---
def main():
    st.header("🔎 Advanced Academic Search Query Generator")

    # --- Session State Initialization ---
    if "history" not in st.session_state:
        st.session_state.history = initialize_history()
    if "latest_explanation" not in st.session_state:
        st.session_state.latest_explanation = ""
    if "query_variations" not in st.session_state:
        st.session_state.query_variations = [] # List to hold multiple queries
    if "search_platform" not in st.session_state:
        st.session_state.search_platform = "JSTOR" # Default platform
    if "num_variations" not in st.session_state:
        st.session_state.num_variations = 1 # Default variations

    # --- Sidebar Controls ---
    with st.sidebar:
        st.subheader("⚙️ Settings")

        # Platform Selection Dropdown
        new_platform = st.selectbox(
            "Select Search Platform:",
            ("JSTOR", "Google Scholar"),
            index=["JSTOR", "Google Scholar"].index(st.session_state.search_platform), # Set current value
            key="platform_selector" # Assign a key for stability
        )
        # If platform changed, update state and clear old results
        if new_platform != st.session_state.search_platform:
            st.session_state.search_platform = new_platform
            st.session_state.latest_explanation = ""
            st.session_state.query_variations = []
            st.session_state.history = initialize_history() # Optionally clear history on platform change
            st.rerun() # Rerun to reflect changes immediately


        # Query Variations Slider
        st.session_state.num_variations = st.slider(
            "Number of Query Variations:",
            min_value=1,
            max_value=10,
            value=st.session_state.num_variations, # Set current value
            step=1
        )

        # Clear Chat History Button
        if st.button("Clear Chat History"):
            st.session_state.history = initialize_history()
            st.session_state.latest_explanation = ""
            st.session_state.query_variations = []
            # Keep platform and num_variations settings
            st.rerun()

    # --- Main Area ---
    st.info(f"Generating queries for: **{st.session_state.search_platform}** | Variations requested: **{st.session_state.num_variations}**")


    # Display chat history (skipping the system prompt)
    display_history(st.session_state.history)

    # Get new user message
    user_input = st.chat_input(f"I want to research on {st.session_state.search_platform} about...")

    if user_input:
        # Add user message to history for display
        st.session_state.history = newMsgToHistory(user_input, st.session_state.history)
        st.chat_message("user").write(user_input)

        # --- Prepare for API Call ---
        # Determine the correct base system prompt
        base_system_prompt = JSTOR_SYSTEM_PROMPT if st.session_state.search_platform == "JSTOR" else GOOGLE_SCHOLAR_SYSTEM_PROMPT

        # Format the instruction for multiple queries
        multi_query_formatted_instruction = MULTI_QUERY_INSTRUCTION.format(
            num_variations=st.session_state.num_variations,
            platform_name=st.session_state.search_platform
        )

        # Combine base prompt, multi-query instruction, and the latest user input
        # We send the system prompt + instruction as the *first* message in a *temporary* list for the API
        api_call_history = [
            {
                "role": "system",
                "content": base_system_prompt + "\n" + multi_query_formatted_instruction
            }
        ]
        # Append the actual conversation history (user messages and previous assistant replies)
        # Filter out any previous system messages just in case
        api_call_history.extend([msg for msg in st.session_state.history if msg["role"] != "system"])


        # Generate the AI's response
        with st.spinner(f"Generating {st.session_state.num_variations} query variation(s) for {st.session_state.search_platform}..."):
            # Pass the specifically constructed history to the API
            updated_history = generate(api_call_history) # Pass the temporary history

            # If API call was successful and returned updated history
            if updated_history and updated_history[-1]["role"] == "assistant":
                 # Add only the latest assistant response to the *permanent* session state history
                 st.session_state.history.append(updated_history[-1])

                 # --- Parse the Response ---
                 last_message = updated_history[-1]
                 response_text = last_message.get("content", "")

                 # Extract explanation (text before the first <query> tag)
                 first_query_tag_index = response_text.find("<query>")
                 if first_query_tag_index != -1:
                     st.session_state.latest_explanation = response_text[:first_query_tag_index].strip()
                 else:
                     # If no query tags found, assume the whole response is explanation (or an error message from the AI)
                     st.session_state.latest_explanation = response_text.strip()
                     st.session_state.query_variations = [] # Clear previous queries if none found

                 # Extract all queries using regex
                 # re.DOTALL makes '.' match newline characters as well
                 queries_found = re.findall(r"<query>(.*?)</query>", response_text, re.DOTALL)
                 # Clean up whitespace within each found query
                 st.session_state.query_variations = [q.strip() for q in queries_found]


            else:
                 # Handle API failure - error messages are shown by generate()
                 st.session_state.latest_explanation = ""
                 st.session_state.query_variations = []


    # --- Display Results --- (Outside the user_input block to persist display)

    # Display explanation persistently below chat history
    if st.session_state.latest_explanation:
        with st.expander("View Explanation", expanded=False): # Default collapsed
            st.write(st.session_state.latest_explanation)

    # Display the final query variations
    if st.session_state.query_variations:
        st.markdown("---") # Separator
        st.markdown(f"**Generated Query Variations for {st.session_state.search_platform}:**")

        for i, query in enumerate(st.session_state.query_variations):
            st.markdown(f"**Variation {i+1}:**")
            st.code(query, language="text")

            # URL encode the query for the link button
            encoded_query = urllib.parse.quote_plus(query)

            # Generate platform-specific link button
            if st.session_state.search_platform == "JSTOR":
                button_label = f"🔍 Try Variation {i+1} on JSTOR"
                button_url = f"https://www.jstor.org/action/doBasicSearch?Query={encoded_query}&so=rel"
            else: # Google Scholar
                button_label = f"🔍 Try Variation {i+1} on Google Scholar"
                button_url = f"https://scholar.google.com/scholar?q={encoded_query}"

            st.link_button(button_label, button_url)
            st.markdown("---") # Separator between variations


if __name__ == "__main__":
    main()
