import json

with open("chunks.json", encoding="utf-8") as f:
    data = json.load(f)

nodes = {n["id"]: n for n in data["nodes"]}
chunks = data["chunks"]

# 1. Chapter list with chunk counts
print("=== CHAPTERS ===")
for n in data["nodes"]:
    if n["type"] == "chapter":
        count = sum(1 for c in chunks if c["node_id"] == n["id"])
        print(f"  [{n['id']}] {n['title'][:50]} | page {n['page_start']} | {count} chunks")

# 2. Suspiciously short chunks (noise candidates)
print("\n=== SHORT CHUNKS (under 50 chars) ===")
short = [c for c in chunks if len(c["content"]) < 50]
print(f"  {len(short)} total")
for c in short[:20]:
    print(f"  p{c['page']}: {c['content']!r}")

# 3. Sample 3 random body chunks to eyeball quality
import random
print("\n=== RANDOM SAMPLE ===")
for c in random.sample(chunks, 3):
    node = nodes.get(c["node_id"], {})
    print(f"\n  [{node.get('title','?')[:40]}] p{c['page']}:")
    print(f"  {c['content'][:200]}")