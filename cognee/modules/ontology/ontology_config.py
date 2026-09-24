from typing import TYPE_CHECKING, Optional, TypedDict

from cognee.modules.ontology.base_ontology_resolver import BaseOntologyResolver
from cognee.modules.ontology.matching_strategies import MatchingStrategy

if TYPE_CHECKING:
    from cognee.modules.teleology.teleology_config import TeleologyConfig


class OntologyConfig(TypedDict, total=False):
    """Configuration containing ontology resolver.

    Attributes:
        ontology_resolver: The ontology resolver instance to use
        ontology_mode: How strictly to apply the ontology for this call —
            "annotate" (enrich only, the default) or "strict" (drop extracted
            entities with no ontology grounding). Falls back to the
            ONTOLOGY_MODE environment value when omitted.
    """

    ontology_resolver: Optional[BaseOntologyResolver]
    ontology_mode: Optional[str]


class Config(TypedDict, total=False):
    """Top-level configuration dictionary.

    Attributes:
        ontology_config: Configuration containing ontology resolver
    """

    ontology_config: Optional[OntologyConfig]
    teleology_config: Optional["TeleologyConfig"]
