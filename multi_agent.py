import os
from dotenv import load_dotenv
from typing import TypedDict, Annotated
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_tavily import TavilySearch
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

# 1. تحميل متغيرات البيئة
load_dotenv()

# 2. تصميم الذاكرة المعمارية (State)
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    sender: str

# 3. إعداد أدوات الباحث
tavily_tool = TavilySearch(max_results=3)
tools = [tavily_tool]
tool_node = ToolNode(tools)

# 4. تهيئة نماذج الذكاء الاصطناعي
# الباحث (دقيق للبحث واستخدام الأدوات)
researcher_llm = ChatGoogleGenerativeAI(model="gemini-3.8-flash", temperature=0).bind_tools(tools)
# المحلل (مساحة أكبر للتحليل الإبداعي والاستراتيجي)
analyst_llm = ChatGoogleGenerativeAI(model="gemini-3.8-flash", temperature=0.2)

# 5. التوجيهات الصارمة (System Prompts)
RESEARCHER_PROMPT = """You are an expert Web Research Agent. 
Your ONLY job is to search the internet using the provided tool to gather raw facts, pricing details, features, and customer reviews about the requested competitor.
DO NOT write the final report. Once you have enough raw data, summarize it briefly for the Analyst.
"""

ANALYST_PROMPT = """You are a Senior Competitive Intelligence Analyst. You DO NOT have access to search tools.
Read the raw data gathered by the Researcher. 
If the data is insufficient (e.g., missing pricing or reviews), specify what is missing so the Researcher can find it (DO NOT say 'FINAL ANSWER').
If the data is complete, compile a structured, analytical final report strictly in English covering: 
1. Pricing model and subscription tiers.
2. Core competitive advantages and key features.
3. Target audience and product weaknesses.
4. Market gaps and opportunities.
CRITICAL: When your final report is complete and ready for the user, you MUST end your entire response with the exact phrase: FINAL ANSWER.
"""

# 6. هندسة العُقد (Nodes)
def researcher_node(state: AgentState):
    # حقن توجيه الباحث لحظياً دون حفظه في الذاكرة المشتركة
    messages = [SystemMessage(content=RESEARCHER_PROMPT)] + state["messages"]
    response = researcher_llm.invoke(messages)
    # إرجاع رد النموذج فقط ليتراكم في الذاكرة، مع تحديث اسم المرسل
    return {"messages": [response], "sender": "researcher"}

def analyst_node(state: AgentState):
    # حقن توجيه المحلل لحظياً
    messages = [SystemMessage(content=ANALYST_PROMPT)] + state["messages"]
    response = analyst_llm.invoke(messages)
    return {"messages": [response], "sender": "analyst"}

# 7. صانع القرار (Router Logic)
def router(state: AgentState) -> str:
    messages = state["messages"]
    last_message = messages[-1]
    
    # إذا طلب الوكيل تشغيل أداة
    if last_message.tool_calls:
        return "call_tool"
        
    # إذا كان التقرير مكتملاً ويحتوي على كلمة السر
    if isinstance(last_message.content, str) and "FINAL ANSWER" in last_message.content:
        return "end"
        
    # تبادل الأدوار (Ping-Pong Effect)
    if state["sender"] == "researcher":
        return "continue_to_analyst"
    elif state["sender"] == "analyst":
        return "continue_to_researcher"

# 8. هندسة الرسم البياني (Graph Topology)
workflow = StateGraph(AgentState)

workflow.add_node("Researcher", researcher_node)
workflow.add_node("Analyst", analyst_node)
workflow.add_node("call_tool", tool_node)

workflow.set_entry_point("Researcher")

workflow.add_conditional_edges(
    "Researcher",
    router,
    {
        "call_tool": "call_tool",
        "continue_to_analyst": "Analyst",
        "end": END
    }
)

workflow.add_conditional_edges(
    "Analyst",
    router,
    {
        "continue_to_researcher": "Researcher",
        "end": END
    }
)

workflow.add_edge("call_tool", "Researcher")

# --- التعديل هنا: استبدال سطر الـ compile العادي بنظام الذاكرة ---
# تفعيل نظام حفظ الذاكرة (Checkpointer)
memory = MemorySaver()
multi_agent_system = workflow.compile(checkpointer=memory)

# 9. حلقة التشغيل والمراقبة
if __name__ == "__main__":
    from langgraph.errors import GraphRecursionError
    
    print("🤖 Welcome to the Multi-Agent Competitive Intelligence System\n")
    print("👥 Team: [Researcher Agent] 🔄 [Strategic Analyst Agent]")
    print("-" * 60)
    
    comp_name = input("📌 Enter competitor name: ")
    comp_url = input("🔗 Enter competitor official URL: ")
    
    print("\n⏳ Team is mobilized and communicating... Please wait.\n")
    
    initial_input = f"Analyze this competitor: {comp_name} | URL: {comp_url}"
    initial_state = {"messages": [HumanMessage(content=initial_input)], "sender": "user"}
    
    # دمج إعدادات الجلسة (thread_id) مع حد الحلقات (recursion_limit)
    run_config = {"configurable": {"thread_id": "session_1"}, "recursion_limit": 15}
    
    try:
        # تمرير run_config هنا
        for event in multi_agent_system.stream(initial_state, config=run_config):
            for node_name, node_state in event.items():
                if node_name == "Researcher":
                    last_msg = node_state["messages"][-1]
                    if last_msg.tool_calls:
                        print(f"🕵️‍♂️ [RESEARCHER] is searching for: '{last_msg.tool_calls[0]['args']['query']}'")
                    else:
                        print(f"🕵️‍♂️ [RESEARCHER] finished gathering data. Handing off to Analyst ->")
                
                elif node_name == "call_tool":
                    print(f"✅ [SYSTEM] Web data retrieved.")
                    print("-" * 30)
                    
                elif node_name == "Analyst":
                    last_msg = node_state["messages"][-1]
                    if "FINAL ANSWER" in last_msg.content:
                        print(f"\n🧠 [ANALYST] Final Report is ready!\n")
                        print("=" * 60)
                        clean_report = last_msg.content.replace("FINAL ANSWER", "").strip()
                        print(clean_report)
                    else:
                        print(f"🧠 [ANALYST] needs more info. Sending back to Researcher <-")
                        
    except GraphRecursionError:
        print("\n[SYSTEM ALERT] Maximum iteration limit reached (15 cycles).")
        
        # 🟢 تطبيق مهارة العنصر البشري (Human-in-the-Loop)
        print("🕵️‍♂️ [RESEARCHER] I couldn't find all the required details (like pricing or reviews) within the allowed search limit.")
        user_decision = input("❓ Do you want the Analyst to generate a partial report with the data gathered so far? (yes/no): ").strip().lower()
        
        if user_decision in ['yes', 'y']:
            print("\n🧠 [ANALYST] Understood. Generating the best possible partial report...\n")
            print("=" * 60)
            
            current_memory = multi_agent_system.get_state(run_config).values.get("messages", [])
            if not current_memory:
                current_memory = initial_state["messages"]
                
            gathered_facts = "\n".join([msg.content for msg in current_memory if isinstance(msg.content, str) and msg.content.strip()])
            
            fallback_text = f"""
            The recursion limit was reached. Here is all the raw data gathered so far:
            
            {gathered_facts}
            
            You must immediately output the final competitive report based ONLY on the data above. Do not ask for more data. End with FINAL ANSWER.
            """
            
            fallback_messages = [
                SystemMessage(content=ANALYST_PROMPT),
                HumanMessage(content=fallback_text)
            ]
            
            # --- 👇 هذا هو الجزء الذي تم تعديله 👇 ---
            fallback_response = analyst_llm.invoke(fallback_messages)
            
            # معالجة ذكية لنوع المخرجات (تأمين ضد تحويل Gemini للنص إلى قائمة)
            raw_content = fallback_response.content
            if isinstance(raw_content, list):
                # استخراج النص من القائمة
                text_content = "".join([str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in raw_content])
            else:
                text_content = str(raw_content)
                
            print(text_content.replace("FINAL ANSWER", "").strip())
            # --- 👆 نهاية الجزء المعدل 👆 ---
            
        else:
            # إذا رفض المستخدم
            print("\n🛑 [SYSTEM] Operation aborted by the user. You can try again with a more specific URL or competitor name.")