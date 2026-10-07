# Agentic Architect Challenge

Submission for the Developer Intern assessment. The repository covers all three parts.

| Part | Topic | Where |
|---|---|---|
| 1 | System design: customer support email agent | `docs/part1_architecture.png` and the 1-page PDF |
| 2 | Web page summarizer (scraping fix and length guardrail) | `part2/summarizer.py` |
| 3 | Working agent with memory and a tool | `agent.py`, `test_calculator.py` |

## Project structure

```
cloudnest-agent/
├── agent.py                 # Part 3: Q&A agent (memory + calculator tool)
├── test_calculator.py       # Tests for the calculator tool
├── test_connection.py       # Quick check that the Gemini API key works
├── data/
│   └── cloudnest_policy.md  # Sample document (fictional company)
├── part2/
│   └── summarizer.py        # Part 2: fixed scraper and summarizer
├── docs/
│   └── part1_architecture.png
├── requirements.txt
└── README.md
```

## Setup

Requirements: Python 3.10 or newer and a free Gemini API key from https://aistudio.google.com.

```bash
python -m venv venv
# Windows PowerShell: venv\Scripts\Activate.ps1
# macOS / Linux:      source venv/bin/activate
pip install -r requirements.txt
```

Create a file named `.env` in the project root:

```
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash
```

The model name is configurable because available model names change over time. Never commit `.env`.

## Running

```bash
python test_connection.py              # should print a short greeting
python agent.py                        # Part 3: interactive agent, type 'exit' to quit
python test_calculator.py              # unit tests (needs GEMINI_API_KEY to be set)
python part2/summarizer.py <url>       # Part 2: summarize a web page
```

Logs are written to `agent.log` and `summarizer.log`.

### Suggested demo for Part 3

1. `Hi, my name is Kyaw Su.` (memory)
2. `How do I cancel my subscription?` (answered from the document, no tool call)
3. `I have the Annual plan and cancel after 5 months. How much refund do I get?` (calculator tool is called, result $105.00)
4. `What is your phone number?` (not in the document, so the agent says it does not know)
5. `What is my name?` (remembered from step 1)

## Part 3 design

- **Grounding:** the policy document is placed in the system prompt, and the rules tell the model to answer only from it and never guess.
- **Memory:** a Gemini chat session (`client.chats.create`) keeps the conversation history.
- **Tool use:** `calculator` is registered as a tool. The model decides whether to call it. The rules limit it to questions that need arithmetic.
- **Safe calculator:** expressions are parsed with `ast` and only basic arithmetic is allowed. `eval()` is not used. Huge exponents are rejected.
- **Reliability and observability:** API errors are caught and logged without crashing. Every tool call and every question and answer is logged. Temperature is 0 for factual answers.

## Part 2 design

Bottlenecks in the original script and the fixes:

| Bottleneck | Fix |
|---|---|
| No timeout, retry or error handling | `fetch_html`: timeout, retry with exponential backoff, status check |
| Menus, ads and scripts mixed into the text | `extract_main_text` keeps only the main content (trafilatura) |
| Long pages exceed the LLM context limit | `chunk_text` plus map-reduce summarization |
| JavaScript-rendered pages return almost no text | Detected and reported with a clear error |
| No control over summary length | `enforce_length`: checked in code, rewrite request, then truncation |

## Trade-offs and known limitations

- Conversation memory lives in the running process only. It is lost when the program exits. A database would fix this at the cost of more complexity.
- The whole sample document is sent in every request. This is fine for one short document. A larger knowledge base would need retrieval (RAG), as described in Part 1.
- The scraper retries on all request errors, including 404 and 403, where retrying does not help. Skipping retries for those status codes is a known improvement.
- JavaScript-rendered pages are detected but not rendered. Rendering with Playwright is the next step.
- The free Gemini tier has rate limits, so heavy use may return 429 errors.

## Notes

CloudNest is a fictional company created for this assessment. The sample document contains no real customer data.