import re
from typing import List

MAX_TEXT_LENGTH = 2000 # 2000 chars (~500 tokens)

def clean_text(text: str) -> str:
    """Cleans the input text by removing URLs, emojis, mentions, and hashtags."""
    if not text or not isinstance(text, str):
        return ""

    # Remove URLs
    text = re.sub(r'https?://[\w/\-?=%.]+\.[\w/\-?=%.]+', '', text)
    
    # Remove mentions
    text = re.sub(r'@\w+', '', text)
    
    # Remove hashtags
    text = re.sub(r'#\w+', '', text)
    
    # A basic emoji pattern
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE,
    )
    text = emoji_pattern.sub(r'', text)

    # Clean up whitespace and normalize
    text = re.sub(r'\s+', ' ', text).strip()

    # If text is too short after cleaning, return empty string
    if len(text) < 3:  # Minimum meaningful text length
        return ""

    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH] + "..."

    return text


def split_text_safely(text: str, max_chunk_size: int = 4096) -> List[str]:
    """
    Split long text into reasonably sized chunks without breaking common
    formatting constructs. Works with plain text, Markdown, or simple HTML.
    """
    if len(text) <= max_chunk_size:
        return [text]
    
    chunks = []
    current_chunk = ""
    
    # Split by paragraphs first (double newlines)
    paragraphs = text.split('\n\n')
    
    for paragraph in paragraphs:
        # If adding this paragraph would exceed chunk size
        if len(current_chunk) + len(paragraph) + 2 > max_chunk_size:  # +2 for \n\n
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            
            # If paragraph itself is too long, split by sentences
            if len(paragraph) > max_chunk_size:
                sentences = paragraph.split('\n')
                for sentence in sentences:
                    if len(current_chunk) + len(sentence) + 1 > max_chunk_size:  # +1 for \n
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                            current_chunk = ""
                        
                        # If sentence is still too long, split more carefully
                        if len(sentence) > max_chunk_size:
                            # Find safe split points (avoid breaking markdown entities)
                            words = sentence.split(' ')
                            for word in words:
                                if len(current_chunk) + len(word) + 1 > max_chunk_size:
                                    if current_chunk:
                                        chunks.append(current_chunk.strip())
                                        current_chunk = word
                                    else:
                                        # Even single word is too long, force split
                                        chunks.append(word[:max_chunk_size])
                                        current_chunk = word[max_chunk_size:]
                                else:
                                    if current_chunk:
                                        current_chunk += " " + word
                                    else:
                                        current_chunk = word
                        else:
                            if current_chunk:
                                current_chunk += "\n" + sentence
                            else:
                                current_chunk = sentence
                    else:
                        if current_chunk:
                            current_chunk += "\n" + sentence
                        else:
                            current_chunk = sentence
            else:
                current_chunk = paragraph
        else:
            if current_chunk:
                current_chunk += "\n\n" + paragraph
            else:
                current_chunk = paragraph
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks 