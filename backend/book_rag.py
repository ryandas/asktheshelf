from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from langchain.tools import tool
from langchain.messages import ToolMessage, HumanMessage
from langchain_huggingface import HuggingFaceEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.models import Distance
from langchain_qdrant import QdrantVectorStore
from langgraph.checkpoint.memory import MemorySaver
from dotenv import load_dotenv
from typing import Dict, Any
import os
load_dotenv()


embedder = HuggingFaceEmbeddings(
    model="sentence-transformers/all-mpnet-base-v2",
    model_kwargs={"device": "cpu"},
)

client = QdrantClient(
    url=os.environ['QDRANT_CLUSTER_ENDPOINT'],
    api_key=os.environ['QDRANT_API_KEY']
)

qdrant = QdrantVectorStore(
    client=client,
    collection_name='books',
    embedding=embedder,
    distance=Distance.COSINE
)

model = init_chat_model(
    model=os.environ['LIGHT_MODEL'],
    model_provider='anthropic',
    max_tokens=1000,
    streaming=True,
)

system_prompt = (
    "You are a helpful AI assistant that answers questions about Data Engineering and Spark "
    "You have access to a tool that retrieves relevant context from text books. "
    "Use the tool to find relevant information before answering questions. "
    "Always cite the sources you use in your answers. "
    "If you cannot find the answer in the retrieved documentation, say so."
)


@tool(response_format="content_and_artifact")
def retrieve_context(query: str):
    """
    Searches the book collection for relevant passages and context matching the given query.
    Use this tool to find information from books that answers user questions.
    """
    retrieved_docs = qdrant.as_retriever().invoke(input=query, k=4)

    serialized = "\n\n".join(
        (f"Source: {doc.metadata.get('source')}\n\nContent: {doc.page_content}")
        for doc in retrieved_docs
    )

    return serialized, retrieved_docs


_memory = MemorySaver()
_agent = create_agent(model, tools=[retrieve_context], system_prompt=system_prompt, checkpointer=_memory)


async def run_agent_streaming(query: str, thread_id: str):
    """Yields (token, None) for streamed tokens, (None, docs) when retrieval completes."""
    config = {"configurable": {"thread_id": thread_id}}

    async for event in _agent.astream_events(
        {"messages": [HumanMessage(content=query)]},
        config=config,
        version="v2",
    ):
        kind = event["event"]

        if kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            content = chunk.content
            if isinstance(content, str) and content:
                yield (content, None)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")
                        if text:
                            yield (text, None)

        elif kind == "on_tool_end" and event["name"] == "retrieve_context":
            output = event["data"].get("output")
            if isinstance(output, tuple) and len(output) == 2:
                _, docs = output
                if isinstance(docs, list):
                    yield (None, docs)
            elif hasattr(output, "artifact") and isinstance(output.artifact, list):
                yield (None, output.artifact)


def run_agent(query: str) -> Dict[str, Any]:
    response = _agent.invoke(
        {"messages": [HumanMessage(content=query)]},
        config={"configurable": {"thread_id": "cli"}},
    )

    answer = response["messages"][-1].content
    context_docs = []
    for message in response["messages"]:
        if isinstance(message, ToolMessage) and hasattr(message, "artifact"):
            if isinstance(message.artifact, list):
                context_docs.extend(message.artifact)

    return {"answer": answer, "context": context_docs}


if __name__ == '__main__':
    query = input("Ask away: ")
    result = run_agent(query=query)
    print(f"{result.get('answer')}\n\n{result.get('context')}")
