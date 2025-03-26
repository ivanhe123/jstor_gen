import streamlit as st
import requests
import json
import re  # Import regular expressions
import urllib.parse  # Import URL encoding

# --- Page Configuration (Set First) ---
st.set_page_config(
    page_title="Advanced Search Query Generator",
    page_icon="🔍",
    layout="wide" # Use wide layout for potentially longer lists of queries
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
    """Calls the OpenRouter API to generate the AI's response."""
    api_key = st.secrets.get("API")
    if not api_key:
        st.error("API key not found. Please set the 'API' secret in Streamlit.")
        return None # Return None to indicate failure

    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            data=json.dumps({
                "model": "google/gemini-pro", # Using a standard model
                "messages": history,
                # "temperature": 0.7, # Optional: Adjust creativity
            }),
            timeout=60 # Add a timeout (in seconds)
        )
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

        response_data = response.json()

        if "choices" in response_data and response_data["choices"]:
            res = response_data["choices"][0]["message"]
            # Add assistant's response back to a *copy* of history to return
            # Avoid modifying the list passed in directly if it's used elsewhere
            updated_history = history + [{
                "role": res.get("role", "assistant"),
                "content": res.get("content", "")
            }]
            return updated_history
        else:
            st.error(f"API response missing 'choices'. Response: {response_data}")
            return None # Indicate failure

    except requests.exceptions.Timeout:
        st.error("API request timed out. Please try again.")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"API request failed: {e}")
        return None
    except json.JSONDecodeError:
        st.error(f"Failed to decode API response. Response text: {response.text}")
        return None
    except Exception as e:
        st.error(f"An unexpected error occurred during API call: {e}")
        return None

# --- History Management ---
def newMsgToHistory(msg, history):
    """Appends a new user message to the history list."""
    history.append({
        "role": "user",
        "content": msg
    })
    return history

def display_history(history):
    """Displays the chat history, skipping system messages."""
    for message in history:
        if message["role"] == "system":
            continue
        role = message["role"]
        content = message.get("content", "") # Use .get for safety
        st.chat_message(role).write(content)

def initialize_history():
    """Initializes an empty conversation history."""
    return []

# --- Main App Logic ---
def main():
    st.header("🔎 Advanced Search Query Generator")

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
        # Use a temporary variable to detect change
        selected_platform = st.selectbox(
            "Select Search Platform:",
            ("JSTOR", "Google Scholar"),
            index=["JSTOR", "Google Scholar"].index(st.session_state.search_platform),
            key="platform_selector"
        )
        # Check if the platform selection has changed
        if selected_platform != st.session_state.search_platform:
            st.session_state.search_platform = selected_platform
            # Clear results and history when platform changes for clarity
            st.session_state.latest_explanation = ""
            st.session_state.query_variations = []
            st.session_state.history = initialize_history()
            st.rerun() # Rerun immediately to reflect the change and clear display

        # Query Variations Slider
        st.session_state.num_variations = st.slider(
            "Number of Query Variations:",
            min_value=1,
            max_value=10,
            value=st.session_state.num_variations,
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

    # Display chat history (current state)
    display_history(st.session_state.history)

    # Get new user message input
    user_input = st.chat_input(f"I want to research on {st.session_state.search_platform} about...")

    if user_input:
        # 1. Update history with user message for display *before* API call
        st.session_state.history = newMsgToHistory(user_input, st.session_state.history)
        # Immediately display the user's message
        st.chat_message("user").write(user_input)

        # 2. Prepare for API Call
        # Determine the correct base system prompt
        base_system_prompt = JSTOR_SYSTEM_PROMPT if st.session_state.search_platform == "JSTOR" else GOOGLE_SCHOLAR_SYSTEM_PROMPT
        # Format the instruction for multiple queries
        multi_query_formatted_instruction = MULTI_QUERY_INSTRUCTION.format(
            num_variations=st.session_state.num_variations,
            platform_name=st.session_state.search_platform
        )
        # Construct the message list for the API call
        api_call_history = [
            {
                "role": "system",
                "content": base_system_prompt + "\n" + multi_query_formatted_instruction
            }
        ]
        # Append actual conversation history (filtering out any stray system messages)
        api_call_history.extend([msg for msg in st.session_state.history if msg["role"] != "system"])

        # 3. Call API and Process Response
        with st.spinner(f"Generating {st.session_state.num_variations} query variation(s) for {st.session_state.search_platform}..."):
            # Pass the constructed history to the API
            response_history = generate(api_call_history)

            # If API call was successful and returned history with an assistant response
            if response_history and response_history[-1]["role"] == "assistant":
                # Get the latest assistant response
                assistant_response = response_history[-1]
                # Add *only* the assistant's response to the persistent session state history
                st.session_state.history.append(assistant_response)

                # Parse the content of the assistant's response
                response_text = assistant_response.get("content", "")

                # Extract explanation (text before the first <query> tag)
                first_query_tag_index = response_text.find("<query>")
                if first_query_tag_index != -1:
                    st.session_state.latest_explanation = response_text[:first_query_tag_index].strip()
                else:
                    # If no query tags, assume whole response is explanation or error message
                    st.session_state.latest_explanation = response_text.strip()
                    st.session_state.query_variations = [] # Clear queries if none found

                # Extract all queries using regex (DOTALL matches newlines)
                queries_found = re.findall(r"<query>(.*?)</query>", response_text, re.DOTALL)
                st.session_state.query_variations = [q.strip() for q in queries_found]

            else:
                 # API call failed or returned unexpected format
                 st.error("Failed to generate queries. Please check the error message above or try again.")
                 # Clear previous results on failure
                 st.session_state.latest_explanation = ""
                 st.session_state.query_variations = []
                 # Optionally remove the last user message if generation failed? No, keep it for context.

        # 4. Rerun to display the new assistant message and results
        # This is crucial - it ensures the whole page redraws with updated state
        st.rerun()

    # --- Display Results ---
    # This section runs *every time* the script runs (including after st.rerun)
    # It reads the *current* state of latest_explanation and query_variations

    # Display explanation
    if st.session_state.latest_explanation:
        with st.expander("View Explanation", expanded=False): # Default collapsed
            st.write(st.session_state.latest_explanation)

    # Display the generated query variations
    if st.session_state.query_variations:
        st.markdown("---") # Separator
        st.markdown(f"**Generated Query Variations for {st.session_state.search_platform}:**")

        for i, query in enumerate(st.session_state.query_variations):
            if query: # Only display if query is not empty
                st.markdown(f"**Variation {i+1}:**")
                st.code(query, language="text") # Use st.code for copy button

                try:
                    # URL encode the query safely
                    encoded_query = urllib.parse.quote_plus(query)

                    # Generate platform-specific link button
                    if st.session_state.search_platform == "JSTOR":
                        button_label = f"🔍 Try Variation {i+1} on JSTOR"
                        button_url = f"https://www.jstor.org/action/doBasicSearch?Query={encoded_query}&so=rel"
                    else: # Google Scholar
                        button_label = f"🔍 Try Variation {i+1} on Google Scholar"
                        button_url = f"https://scholar.google.com/scholar?q={encoded_query}"

                    st.link_button(button_label, button_url, key=f"btn_{i}_{query[:10]}") # Add unique key
                    st.markdown("---") # Separator between variations
                except Exception as e:
                    st.error(f"Error creating link for Variation {i+1}: {e}") # Handle potential errors during URL encoding/button creation

# --- Entry Point ---
if __name__ == "__main__":
    main()
