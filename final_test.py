import sys
sys.path.insert(0, ".")
from app import app
from fastapi.testclient import TestClient
client = TestClient(app)

tests = [
    ("Q1: WHY SparkClean spike Mumbai", "Why did SparkClean 1kg primary sales spike in Mumbai in the week of 16 Sep 2025?"),
    ("Q2: WHAT GlucoJoy North Nov", "What were GlucoJoy monthly primary sales vs target in the North region in November 2025?"),
    ("Q3: OOD", "What is the GDP of India?"),
    ("Q4: WTD", "What should we do about GlucoJoy stockouts in Delhi?"),
    ("Q5: WHAT GlucoJoy North Oct", "What were GlucoJoy monthly primary sales vs target in the North region in October 2025?"),
    ("Q6: False premise", "What were sales of ProductXYZ in 2024?"),
]

for name, q in tests:
    r = client.post("/ask", json={"question": q})
    d = r.json()
    ans = d["answer"][:180].replace("\n", " | ").replace("  ", " ")
    print(f"{name}: intent={d['intent']} status={d['status']} conf={d['confidence']} cit={len(d['citations'])}")
    print(f"  {ans}")
    print()