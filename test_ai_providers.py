"""Verify all 5 AI providers loaded from .env"""
import ai_providers

print(f"Total providers: {len(ai_providers.PROVIDERS)}")
print("-" * 70)
for i, p in enumerate(ai_providers.PROVIDERS):
    name = p["name"]
    model = p["model"]
    key_preview = p["api_key"][:10] + "..."
    print(f"  {i+1}. {name:15s} | {model:40s} | {key_preview}")
print("-" * 70)
print(f"AI available: {ai_providers.is_ai_available()}")
