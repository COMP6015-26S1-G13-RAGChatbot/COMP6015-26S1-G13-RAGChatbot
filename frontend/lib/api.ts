import { Source } from "@/types/chat";

const API_BASE_URL = "http://localhost:8000";

export async function fetchChatAnswer(query: string): Promise<{ answer: string; sources: Source[] }> {
  const response = await fetch(`${API_BASE_URL}/ask`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query }),
  });

  if (!response.ok) {
    throw new Error(`API Error: ${response.statusText}`);
  }

  const data = await response.json();

  const formattedSources: Source[] = data.sources.map((s: string, index: number) => {
    const [header, content] = s.split(" | ");
    
    const title = header.trim(); // "[LEGAL] smcs-bylaws.pdf (Page: 4)"
    const text = content?.replace("Snippet: ", "").trim() || s;

    return {
      id: index + 1,
      doc: title.match(/\]\s*(.*?)\s*\(/)?.[1] || "Document", 
      page: title.match(/Page:\s*(\d+)/)?.[1] || "?",          
      text: text,
      type: title.includes("LEGAL") ? "legal" : "operational",
    };
  });

  return {
    answer: data.answer,
    sources: formattedSources,
  };
}