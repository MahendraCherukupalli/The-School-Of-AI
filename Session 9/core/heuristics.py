import re


_BRACKETED_MESSAGE_PATTERN = re.compile(r"\[.*\]")
_UNSUCCESSFUL_OUTPUT_PREFIXES = {
    "Unexpected result format from agent:",
    "Max steps reached",
}

# For censor_bad_words
DEFAULT_BAD_WORDS = {
    "Bastard", "Pissed", "Craphead","Dang"
}


# --- Heuristic Functions ---

def is_valid_agent_output(text: str) -> bool:
    """
    Heuristic (ID: H001)
    Checks if the agent's output text is considered valid and not a system error/status message.
    (This logic was previously in agent.py's is_successful_final_answer)
    """
    if not text:  # An empty output is not considered valid for saving as a final answer
        return False

    # Check if the entire text is a bracketed message (e.g., "[Error Message]")
    if _BRACKETED_MESSAGE_PATTERN.fullmatch(text):
        return False

    # Check for known unsuccessful prefixes
    for prefix in _UNSUCCESSFUL_OUTPUT_PREFIXES:
        if text.startswith(prefix):
            return False
            
    return True # If none of the above, assume it's a valid output


def check_url_is_secure(url_string: str) -> bool:
    """
    Heuristic (ID: H002)
    Checks if a URL string likely uses HTTPS.
    Returns True if 'https://' is found at the beginning (case-insensitive, after stripping), False otherwise.
    """
    if not isinstance(url_string, str):
        return False
    return url_string.strip().lower().startswith("https://")


def censor_bad_words(text: str, custom_bad_words: set = None, replacement: str = "***") -> str:
    """
    Heuristic (ID: H003)
    Replaces words from a predefined list (and optional custom list)
    with the replacement string. Case-insensitive.
    """
    if not isinstance(text, str):
        return "" # Or raise an error, depending on desired behavior

    combined_bad_words = DEFAULT_BAD_WORDS.copy()
    if custom_bad_words:
        # Ensure custom words are also lowercase for case-insensitive matching
        combined_bad_words.update(word.lower() for word in custom_bad_words)

    if not combined_bad_words:
        return text

    # Create a regex pattern to find whole words, case-insensitive
    # Using word boundaries (\b) to avoid censoring "badword" in "thisisnotabadwordexample"
    # Sorting by length descending to match longer phrases first (e.g., "very bad" before "bad")
    # Escaping regex special characters in words just in case
    try:
        # Filter out empty strings from combined_bad_words to avoid issues with regex
        valid_bad_words = [word for word in combined_bad_words if word]
        if not valid_bad_words:
            return text
        pattern_str = r'\b(' + '|'.join(re.escape(word) for word in sorted(valid_bad_words, key=len, reverse=True)) + r')\b'
        pattern = re.compile(pattern_str, flags=re.IGNORECASE)
        return pattern.sub(replacement, text)
    except re.error as e:
        # Handle potential regex compilation errors if bad_words list is problematic
        print(f"Regex error in censor_bad_words: {e}. Returning original text.")
        return text


def is_valid_email_format(email_string: str) -> bool:
    """
    Heuristic (ID: H004)
    Uses a simple regex to check for a basic email pattern (e.g., name@domain.com).
    This is a basic check and not fully RFC compliant, but a common heuristic.
    """
    if not isinstance(email_string, str):
        return False
    # A common simple regex for email validation: one or more chars, @, one or more chars, ., 2+ chars
    email_pattern = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    return bool(email_pattern.fullmatch(email_string)) # Use fullmatch for entire string


def is_within_length_limits(text: str, min_length: int = 0, max_length: int = 10240) -> bool:
    """
    Heuristic (ID: H005)
    Checks if the length of the text is within the specified 
    min (inclusive) and max (inclusive) lengths.
    """
    if not isinstance(text, str):
        return False # Or handle as an error (e.g. if min_length > 0, non-string fails)
    length = len(text)
    return min_length <= length <= max_length


def contains_no_digits(text: str) -> bool:
    """
    Heuristic (ID: H006)
    Returns True if the text contains no digit characters (0-9).
    """
    if not isinstance(text, str):
        return True # Or False, or error, depending on how to treat non-strings. True = "no digits found in non-string"
    return not any(char.isdigit() for char in text)


def is_positive_integer_string(text: str) -> bool:
    """
    Heuristic (ID: H007)
    Returns True if the string consists only of digits 
    and represents a positive integer (>0).
    """
    if not isinstance(text, str):
        return False
    return text.isdigit() and int(text) > 0


def is_not_empty_or_whitespace(text: str) -> bool:
    """
    Heuristic (ID: H008)
    Returns True if the string is not None, not empty, 
    and not composed solely of whitespace characters.
    """
    return isinstance(text, str) and text.strip() != ""


def has_balanced_brackets(text: str, open_char: str = '(', close_char: str = ')') -> bool:
    """
    Heuristic (ID: H009)
    A simple counter-based check for balanced specified bracket pairs (e.g. parentheses, square brackets).
    Does not handle nesting correctness for different types of brackets mixed (e.g., "([)]")
    but checks counts for a single type of bracket pair.
    """
    if not isinstance(text, str):
        return True # Or False/error. Assuming non-strings vacuously satisfy this.
    
    balance = 0
    for char in text:
        if char == open_char:
            balance += 1
        elif char == close_char:
            balance -= 1
        if balance < 0:  # A closing bracket appeared before a matching open one
            return False
    return balance == 0  # True if all opened brackets were closed


def is_allowed_tool_name(tool_name: str, allowed_tools_registry: set) -> bool:
    """
    Heuristic (ID: H010)
    Checks if the tool_name (case-sensitive) is present in a set of allowed tools.
    Example for your rule: "Tool name not in the registry?"
    """
    if not isinstance(tool_name, str) or not isinstance(allowed_tools_registry, set):
        # Or raise TypeError for incorrect usage of the heuristic itself
        return False 
    return tool_name in allowed_tools_registry


def check_retry_limit(current_attempts: int, max_attempts: int = 3) -> bool:
    """
    Heuristic (ID: H011) - Bonus heuristic
    Checks if the number of current attempts is less than max attempts, meaning more retries are allowed.
    Example for your rule: "Timeout? Retry? Allow up to 3 times?"
    Returns True if more retries are allowed, False otherwise.
    """
    # Ensure types are correct for comparison
    if not (isinstance(current_attempts, int) and isinstance(max_attempts, int)):
        return False # Or raise TypeError
    return current_attempts < max_attempts
