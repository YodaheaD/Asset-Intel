from app.services.intelligence_processors.registry import ProcessorSpec
from app.services.intelligence_processors.image_metadata import process_image_metadata_run

PROCESSORS: dict[str, ProcessorSpec] = {
    "image-metadata": ProcessorSpec(
        name="image-metadata",
        version="1.0.0",
        handler=process_image_metadata_run,
    )
}
