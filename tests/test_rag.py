import json
import requests
import pandas as pd
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import faithfulness
from ragas.metrics import answer_relevancy
from ragas.metrics.collections import faithfulness, context_recall
# Backend API 
API_URL = "http://localhost:8000/ask"

# Golden SEt 
with open('golden_set.json', 'r', encoding='utf-8') as f:
    golden_set = json.load(f)

evaluation_data = []

print("🚀 Starting RAG Benchmark Evaluation...")

# 3. 50개 질문 순회하며 백엔드 챗봇 엔진에 요청
for item in golden_set:
    query = item['question']
    print(f"Testing {item['id']}: {query[:40]}...")
    
    try:
        # 프론트엔드의 body: JSON.stringify({ query })와 동일한 구조
        response = requests.post(API_URL, json={"query": query}, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            
            # 프론트엔드 파싱 로직 전의 '원문 raw 스트링 배열'을 그대로 contexts로 활용
            # data['sources']는 ['[LEGAL] smcs-bylaws.pdf (Page: 4) | Snippet: ...', ...] 구조
            retrieved_contexts = data.get('sources', [])
            chatbot_answer = data.get('answer', '')
            
            # RAGAS 데이터셋 포맷에 맞게 적재
            evaluation_data.append({
                "question": query,
                "answer": chatbot_answer,
                "contexts": retrieved_contexts,
                "ground_truth": item['ground_truth']
            })
        else:
            print(f"❌ Error at {item['id']}: Status Code {response.status_code}")
            
    except Exception as e:
        print(f"💥 Request failed at {item['id']}: {e}")

# 4. RAGAS Dataset 객체로 변환
df = pd.DataFrame(evaluation_data)
dataset = Dataset.from_pandas(df)

# 5. RAGAS 평가 실행
print("\n📊 Calculating RAGAS Scores (this might take a few minutes)...")
result = evaluate(
    dataset=dataset,
    metrics=[faithfulness, answer_relevancy, context_recall]
)

# 6. 결과 리포트 출력 및 저장
print("\n=== Final Evaluation Results ===")
print(result)

df_result = result.to_pandas()
df_result.to_csv('rag_evaluation_report.csv', index=False)
print("✅ Evaluation complete! Report saved to 'rag_evaluation_report.csv'")