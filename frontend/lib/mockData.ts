import { Message, Source } from "@/types/chat";

export const mockSources: Source[] = [
  {
    id: 1,
    doc: "IEEE_Bylaws.pdf",
    page: 10,
    text: "Section 5.1: The Board of Directors shall consist of not fewer than fifteen (15) nor more than forty-five (45) members, elected by the Members of the Institute in accordance with the provisions of the Constitution.",
  },
  {
    id: 2,
    doc: "IEEE_Constitution.pdf",
    page: 3,
    text: "Article III - Membership: Any person actively engaged in or interested in electrical, electronics, or allied engineering or related arts and sciences may apply for membership in the Institute.",
  },
  {
    id: 3,
    doc: "SMCS_Governance_Policy.pdf",
    page: 22,
    text: "The Systems, Man, and Cybernetics Society shall maintain a Technical Committee structure responsible for the advancement of knowledge in the field of systems science and cybernetics.",
  },
  {
    id: 4,
    doc: "IEEE_Bylaws.pdf",
    page: 47,
    text: "Section 12.3: The Executive Director shall be the chief staff executive of the Institute and shall be responsible for the management of all staff activities and the administration of all programs of the Institute.",
  },
];

export const mockMessages: Message[] = [
  {
    id: "1",
    role: "user",
    content: "Explain the composition of the Board of Directors according to Section 5 of the IEEE Bylaws.",
    timestamp: new Date(Date.now() - 120000),
  },
  {
    id: "2",
    role: "assistant",
    content:
      "According to IEEE Bylaws Section 5, the Board of Directors consists of **at least 15 and no more than 45** directors [1]. These directors are elected by the membership in accordance with Constitutional provisions [1].\n\nRegarding membership eligibility, Article III of the IEEE Constitution states that any person actively engaged or interested in electrical, electronics, or allied engineering and related sciences may apply for membership [2].\n\nAdditionally, the SMCS Governance Policy requires the maintenance of a Technical Committee structure dedicated to advancing knowledge in systems science and cybernetics [3].",
    sources: [mockSources[0], mockSources[1], mockSources[2]],
    timestamp: new Date(Date.now() - 115000),
  },
  {
    id: "3",
    role: "user",
    content: "What are the responsibilities of the Executive Director?",
    timestamp: new Date(Date.now() - 60000),
  },
  {
    id: "4",
    role: "assistant",
    content:
      "Per IEEE Bylaws Section 12.3, the Executive Director serves as the **chief staff executive of the Institute** and is responsible for the following [4]:\n\n- Management of all staff activities\n- Administration of all Institute programs\n- General oversight of Institute operations\n\nThe Executive Director is accountable to the Board of Directors and represents the organization as defined by the Constitution and Bylaws [4][1].",
    sources: [mockSources[3], mockSources[0]],
    timestamp: new Date(Date.now() - 55000),
  },
];

export const mockResponse = {
  answer:
    "According to IEEE Bylaws Section 5, the Board of Directors consists of 15 to 45 members [1], elected directly by the membership. Furthermore, Article III of the IEEE Constitution specifies that anyone in a related engineering field may apply for membership [2].",
  sources: mockSources,
};