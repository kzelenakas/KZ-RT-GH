from app.config import XSD_PATH

from .base import SchemaAdapter
from .placeholder import PlaceholderAdapter
from .uad36_v13 import UAD36v13Adapter


def get_default_adapter() -> SchemaAdapter:
    return UAD36v13Adapter(str(XSD_PATH))


__all__ = ["PlaceholderAdapter", "SchemaAdapter", "UAD36v13Adapter", "get_default_adapter"]
