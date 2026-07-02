from app import config

from .base import SchemaAdapter
from .placeholder import PlaceholderAdapter
from .uad36_v13 import UAD36v13Adapter


def get_default_adapter() -> SchemaAdapter:
    return UAD36v13Adapter(str(config.XSD_PATH), str(config.MANIFEST_PATH))


__all__ = ["PlaceholderAdapter", "SchemaAdapter", "UAD36v13Adapter", "get_default_adapter"]
