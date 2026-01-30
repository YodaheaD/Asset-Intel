from app.services.intelligence_processors.registry import ProcessorSpec
from app.services.intelligence_processors.image_metadata import process_image_metadata_run
from app.services.intelligence_processors.fingerprint import process_fingerprint_run
PROCESSORS: dict[str, ProcessorSpec] = {
    "image-metadata": ProcessorSpec(
        name="image-metadata",
        version="1.0.0",
        handler=process_image_metadata_run,
    )
}

 # Phase 6.1 Addition
PROCESSORS["asset-fingerprint"] = ProcessorSpec(
    name="asset-fingerprint",
    version="1.0.0",
    handler=process_fingerprint_run,
)