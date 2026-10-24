
from typing import TypedDict
from langgraph.graph import StateGraph, START, END


# 1. Define the shared state
class ResearchState(TypedDict):
    topic: str
    country: str
    status: str


# 2. Check whether the research request is complete
def check_request(state: ResearchState):
    print("Checking the research request...")

    if state["country"].strip():
        return {"status": "Request is ready"}
    else:
        return {"status": "Country is missing"}


# 3. Decide which node should run next
def choose_next_step(state: ResearchState):
    if state["status"] == "Request is ready":
        return "start_research"
    else:
        return "report_missing_info"


# 4. The research node
def start_research(state: ResearchState):
    print("Research can begin!")
    return {"status": "Research started"}


# 5. The missing-information node
def report_missing_info(state: ResearchState):
    print("Cannot begin: please provide a country.")
    return {"status": "Waiting for country information"}


# 6. Build the graph
builder = StateGraph(ResearchState)

builder.add_node("check_request", check_request)
builder.add_node("start_research", start_research)
builder.add_node("report_missing_info", report_missing_info)

builder.add_edge(START, "check_request")

builder.add_conditional_edges(
    "check_request",
    choose_next_step,
    {
        "start_research": "start_research",
        "report_missing_info": "report_missing_info",
    },
)

builder.add_edge("start_research", END)
builder.add_edge("report_missing_info", END)

graph = builder.compile()


# 7. Test with a complete research request
result = graph.invoke({
    "topic": "Diabetes",
    "country": "India",
    "status": "",
})

print("\nFinal result:", result)
