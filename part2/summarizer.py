"""Part 2: web page summarizer (fixed version).

ORIGINAL SCRIPT (hypothetical) and why it failed
------------------------------------------------
    html = requests.get(url).text
    text = BeautifulSoup(html, "html.parser").get_text()
    return llm(f"Summarize this: {text}")

Bottlenecks and fixes
---------------------
1. No timeout, retry or error handling -> fetch_html(): timeout, retry with
   exponential backoff, raise_for_status().
2. get_text() keeps menus, ads, footers and script code -> extract_main_text()
   uses trafilatura to keep only the main article text.
3. Long pages exceed the LLM context limit (main bottleneck) -> chunk_text() +
   map-reduce summarization (summarize each chunk, then combine).
4. JavaScript-rendered pages return almost empty HTML -> detected in
   summarize_url() and reported clearly (a Playwright fallback is the
   next step, see README).
5. No length control -> enforce_length() guardrail checks the word count in
   code, asks for a rewrite, and finally truncates.

Run: python part2/summarizer.py [url]
"""

import logging
import os
import sys
import time

import requests
import trafilatura
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

logging.basicConfig(
    filename="summarizer.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("summarizer")

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
MAX_WORDS = 150          # guardrail: maximum words in the final summary
CHUNK_CHARS = 8000       # size of each chunk sent to the LLM
MAX_CHUNKS = 20          # cost guard: ignore text beyond this many chunks
MIN_TEXT_CHARS = 200     # below this, the page is probably JS-rendered or blocked

# Created once at module level so the connection stays open (see Part 3 note).
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


# --- Step 1: fetch ---------------------------------------------------------
def fetch_html(url: str, retries: int = 3, timeout: int = 10) -> str:
    """Download a page, retrying on temporary failures."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SummarizerBot/1.0)"}

    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            logger.warning("Attempt %d/%d failed for %s: %s", attempt, retries, url, exc)
            if attempt < retries:
                time.sleep(2 ** attempt)

    raise RuntimeError(f"Failed to fetch {url} after {retries} attempts")


# --- Step 2: extract the main content --------------------------------------
def extract_main_text(html: str) -> str:
    """Keep the main article text only (no menus, ads or scripts)."""
    text = trafilatura.extract(html, include_comments=False, include_tables=False)
    return text or ""


# --- Step 3: chunking ------------------------------------------------------
def chunk_text(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """Split text into chunks of about `size` characters, at paragraph breaks."""
    chunks, current = [], ""
    for paragraph in text.split("\n"):
        # A single huge paragraph is sliced so no chunk is oversized.
        pieces = [paragraph[i:i + size] for i in range(0, len(paragraph), size)] or [""]
        for piece in pieces:
            if current and len(current) + len(piece) + 1 > size:
                chunks.append(current)
                current = ""
            current += piece + "\n"
    if current.strip():
        chunks.append(current)
    return chunks


# --- Step 4: LLM calls -----------------------------------------------------
def ask_llm(prompt: str, attempts: int = 2) -> str:
    """Call Gemini with a simple retry. Returns the text of the answer."""
    for attempt in range(1, attempts + 1):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0),
            )
            return (response.text or "").strip()
        except Exception as exc:
            logger.warning("LLM attempt %d/%d failed: %s", attempt, attempts, exc)
            if attempt < attempts:
                time.sleep(2 ** attempt)
    raise RuntimeError("LLM call failed after retries")


def summarize_chunk(chunk: str) -> str:
    """MAP step: summarize one chunk."""
    return ask_llm(
        "Summarize the following text in at most 5 sentences. "
        "Use only information from the text.\n\n" + chunk
    )


def combine_summaries(summaries: list[str]) -> str:
    """REDUCE step: merge the partial summaries into one."""
    return ask_llm(
        "Combine these partial summaries into one coherent summary. "
        "Use only the information given.\n\n" + "\n\n".join(summaries)
    )


# --- Step 5: guardrail -----------------------------------------------------
def enforce_length(summary: str, max_words: int = MAX_WORDS) -> str:
    """Guarantee the summary is concise. Checked in code, not just in the prompt."""
    for attempt in range(2):
        if len(summary.split()) <= max_words:
            return summary
        logger.info("Summary too long (%d words), rewrite attempt %d",
                    len(summary.split()), attempt + 1)
        summary = ask_llm(
            f"Rewrite this summary in under {max_words} words. "
            "Keep only the key facts.\n\n" + summary
        )
    words = summary.split()
    if len(words) > max_words:  # last line of defence: hard truncation
        logger.warning("Hard-truncating summary to %d words", max_words)
        return " ".join(words[:max_words]) + "..."
    return summary


# --- Pipeline --------------------------------------------------------------
def summarize_url(url: str) -> str:
    html = fetch_html(url)
    text = extract_main_text(html)
    if len(text) < MIN_TEXT_CHARS:
        # Hypothetical next step: render the page with Playwright and retry.
        raise ValueError(
            "Too little content extracted. The page may need JavaScript "
            "rendering or may block scrapers."
        )

    chunks = chunk_text(text)
    if len(chunks) > MAX_CHUNKS:
        logger.warning("Text has %d chunks, using the first %d", len(chunks), MAX_CHUNKS)
        chunks = chunks[:MAX_CHUNKS]

    partial = [summarize_chunk(c) for c in chunks]
    combined = partial[0] if len(partial) == 1 else combine_summaries(partial)
    return enforce_length(combined)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "https://en.wikipedia.org/wiki/Artificial_intelligence"
    try:
        result = summarize_url(target)
        print(result)
        print(f"\n[{len(result.split())} words]")
    except Exception as exc:
        logger.exception("Summarization failed for %s", target)
        print(f"Error: {exc}")