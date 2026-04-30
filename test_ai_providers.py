"""Quick diagnostic: test each AI provider in the cascade."""
from openai import OpenAI
import ai_providers

for p in ai_providers.PROVIDERS:
    name = p["name"]
    try:
        client = OpenAI(api_key=p["api_key"], base_url=p.get("base_url"))
        resp = client.chat.completions.create(
            model=p["model"],
            messages=[{"role": "user", "content": "Say OK"}],
            max_tokens=5
        )
        print(f"{name}: PASS - {resp.choices[0].message.content}")
    except Exception as e:
        print(f"{name}: FAIL - {str(e)[:300]}")
