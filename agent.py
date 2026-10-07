"""CloudNest support agent.

Answers questions from a single policy document, remembers the conversation
(memory), and calls a calculator tool only when the model decides it needs one.
"""

import ast
import logging
import operator
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# --- Logging (observability): every tool call and error goes to agent.log ---
logging.basicConfig(
    filename="agent.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("cloudnest-agent")

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
POLICY_PATH = Path(__file__).parent / "data" / "cloudnest_policy.md"

# Created once at module level. If it were a local variable inside a function,
# Python would garbage-collect (and close) it as soon as that function returned.
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

SYSTEM_PROMPT = """You are a customer support assistant for CloudNest.

Rules:
1. Answer ONLY using the DOCUMENT below. If the answer is not in the document,
   say you do not have that information. Never guess or invent facts.
2. Use the calculator tool ONLY when the question needs arithmetic
   (for example, a prorated refund amount). If the answer can be read
   directly from the document, do not call the tool.
3. When you calculate a refund, show the formula and the numbers you used.
4. Remember what the user told you earlier in this conversation,
   such as their name, and use it naturally.
"""

# --- Calculator tool: safe arithmetic (no eval on raw input) ---
_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}


def _eval_node(node):
    """Recursively evaluate a parsed arithmetic expression."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("exponent too large")
        return _OPERATORS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_eval_node(node.operand))
    raise ValueError("unsupported expression")


def calculator(expression: str) -> str:
    """Evaluate an arithmetic expression and return the result.

    Use only when a question requires math, such as prorated refund amounts.
    Supports + - * / ** and parentheses. Example: "(200 / 12) * 7 * 0.90".

    Args:
        expression: The arithmetic expression to evaluate.

    Returns:
        The numeric result rounded to 2 decimals, or an error message.
    """
    logger.info("Tool call: calculator(%s)", expression)
    print(f"  [tool used: calculator({expression})]")
    try:
        tree = ast.parse(expression, mode="eval")
        return str(round(_eval_node(tree.body), 2))
    except Exception as exc:  # return the error so the model can recover
        logger.warning("Calculator failed for %r: %s", expression, exc)
        return f"Error: could not calculate ({exc})"


def load_policy() -> str:
    """Read the sample document that the agent answers from."""
    if not POLICY_PATH.exists():
        raise FileNotFoundError(f"Policy document not found at {POLICY_PATH}")
    return POLICY_PATH.read_text(encoding="utf-8")


def create_chat():
    """Create a chat session. The chat object stores the history (memory)."""
    config = types.GenerateContentConfig(
        system_instruction=f"{SYSTEM_PROMPT}\nDOCUMENT:\n{load_policy()}",
        tools=[calculator],  # the model decides whether to call it
        temperature=0,       # lower randomness for factual answers
    )
    return client.chats.create(model=MODEL, config=config)


def main():
    chat = create_chat()
    print("CloudNest assistant ready. Type 'exit' to quit.\n")
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in {"exit", "quit"}:
            break
        if not user_input:
            continue
        try:
            response = chat.send_message(user_input)
            answer = response.text or "Sorry, I could not produce an answer."
            logger.info("Q: %s | A: %s", user_input, answer)
            print(f"Agent: {answer}\n")
        except Exception:
            logger.exception("Gemini call failed")
            print("Agent: Sorry, something went wrong. Please try again.\n")


if __name__ == "__main__":
    main()