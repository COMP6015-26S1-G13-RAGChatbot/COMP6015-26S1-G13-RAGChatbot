export function parseSourceString(sourceStr: string, index: number) {
  const [header, content] = sourceStr.split(" | ");
  const type = header.includes("LEGAL") ? "LEGAL" : "OPERATIONAL";
  
  // extract file name and page 
  const docName = header.replace(`[${type}] `, "").split(" (Page:")[0];
  const page = header.match(/Page:\s*(\d+)/)?.[1] || "?";
  const text = content?.replace("Snippet: ", "").replace(/"/g, "") || "";

  return { id: index, type, docName, page, text };
}