from logging import getLogger

from ..utils.exceptions import ParserExecutionError
from .base import BaseParser

logger = getLogger(__name__)


class GenerationParser(BaseParser):
    """
    An abstract base class for parsers that fetch resources by generation.

    This parser iterates through Pokémon generations and collects all resources
    (abilities, moves, etc.) that were introduced in each generation up to and
    including the target generation.

    This approach is more efficient than fetching from a single large endpoint
    when working with generation-specific data.
    """

    def _get_all_item_refs(self) -> list[dict[str, str]]:
        """
        Retrieves all resource references by iterating through generation endpoints.

        This method queries each generation from 1 to target_gen and collects
        all resources of the parser's type (abilities, moves, etc.) that were
        introduced in those generations.

        Returns:
            A list of resource reference dictionaries with 'name' and 'url' keys
        """
        all_references: list[dict[str, str]] = []
        errors: list[str] = []

        if self.target_gen:
            logger.info(
                f"Collecting all {self.entity_type.lower()}s up to Generation {self.target_gen}..."
            )

            for generation_num in range(1, self.target_gen + 1):
                try:
                    generation_url = (
                        f"{self.config.api_base_url}generation/{generation_num}"
                    )
                    generation_data = self.api_client.get(generation_url)

                    resources_in_gen = generation_data[self.api_endpoint]
                    if not isinstance(resources_in_gen, list):
                        raise ValueError(
                            f"Invalid {self.api_endpoint} resource listing"
                        )
                    all_references.extend(resources_in_gen)

                    logger.debug(
                        f"Generation {generation_num}: Found {len(resources_in_gen)} {self.entity_type.lower()}(s)"
                    )

                except Exception as e:
                    logger.error(
                        f"Failed to fetch {self.entity_type} data for Generation {generation_num}: {e}"
                    )
                    errors.append(f"Generation {generation_num}: {e}")

        if errors:
            raise ParserExecutionError(
                f"Could not collect complete {self.entity_type} references: "
                + "; ".join(errors)
            )

        return all_references
