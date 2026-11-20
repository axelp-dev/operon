# ==========================================================
#                   AI MODELS
# ==========================================================

from langchain_ollama import ChatOllama


# Qwen3:4b ollama model
qwen_llm = ChatOllama(model="qwen3:4b", temperature=0, reasoning=False)

qwen_llm_25 = ChatOllama(
    model="qwen2.5:3b",
    temperature=0,
    num_ctx=3072,
    num_predict=300,
    keep_alive="2m",
)
