from langchain_ollama import OllamaLLM  
from langchain_core.callbacks import StreamingStdOutCallbackHandler
# from langchain.callbacks.manager import CallbackManager
# from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler

class LLMService:
    def __init__(self):
        # local llm (Ollama)
        self.llm = OllamaLLM(
            model="llama3", 
            callbacks=[StreamingStdOutCallbackHandler()],
            temperature=0
        )

    def generate_answer(self, query, context_dict):

        legal_text = "\n".join([d.page_content for d in context_dict.get('legal', [])])
        op_text = "\n".join([d.page_content for d in context_dict.get('operational', [])])
        gen_text = "\n".join([d.page_content for d in context_dict.get('general', [])])

        prompt = f"""
        ### ROLE
        You are a strict Policy Compliance Auditor for the IEEE SMC Society. 
        Your goal is to cross-check the [OPERATIONAL MANUAL] against the [LEGAL (Constitution/Bylaws)].

        ### CONTEXT: LEGAL (The Supreme Law)
        {legal_text if legal_text else "No legal records found."}

        ### CONTEXT: OPERATIONAL MANUAL (Subordinate Rules)
        {op_text if op_text else "No operational records found."}
        
        ### AUDIT INSTRUCTIONS
        1. **Check for Authorization**: Does the LEGAL context explicitly authorize the bodies or rules mentioned in the MANUAL?
        2. **Identify Conflicts**: If the MANUAL describes a body (e.g., SMCS-TAB) or a rule that is NOT found in the LEGAL context, flag it as "Potentially unauthorized or inconsistent."
        3. **Strict Differentiation**: Treat 'IEEE TAB' (General IEEE body) and 'SMCS-TAB' (Specific Society body) as different entities. Check if SMCS-TAB is formally defined in the Constitution.
        4. **Hierarchy of Truth**: If there is a mismatch, the LEGAL context always prevails.

        ### QUESTION
        {query}
        
        ### RESPONSE (Focus on identifying missing legal basis or direct contradictions):"""
        
        return self.llm.invoke(prompt)