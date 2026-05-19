export interface Source {
  id: number;
  doc: string;
  page: number;
  text: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  timestamp: Date;
  isLoading?: boolean;
}

export interface CitationProps {
  sourceId: number;
  onClick: (id: number) => void;
  isActive: boolean;
}