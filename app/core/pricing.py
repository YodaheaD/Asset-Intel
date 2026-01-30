# cents, intentionally simple
PROCESSOR_PRICING = {
    "image-metadata": 100,  # $1.00 per run
    "asset-fingerprint": 50,  # $0.50 per run
}

def estimate_cost(processor_name: str) -> int:
    return PROCESSOR_PRICING.get(processor_name, 0)
