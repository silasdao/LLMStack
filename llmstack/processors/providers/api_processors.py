import logging

from .api_processor_interface import ApiProcessorInterface

logger = logging.getLogger(__name__)


class ApiProcessorFactory:
    """
    Factory class for API processors
    """
    @staticmethod
    def get_api_processor(processor_slug, provider_slug=None) -> ApiProcessorInterface:
        subclasses = ApiProcessorInterface.__subclasses__()
        return next(
            (
                subclass
                for subclass in subclasses
                if subclass.slug() == processor_slug
                and subclass.provider_slug() == provider_slug
            ),
            None,
        )
