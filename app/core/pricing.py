# cents, intentionally simple
PROCESSOR_PRICING = {
    "image-metadata": 1,  # $0.01 per run
}

def estimate_cost(processor_name: str) -> int:
    return PROCESSOR_PRICING.get(processor_name, 0)
