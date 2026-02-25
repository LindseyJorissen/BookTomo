from dataclasses import dataclass, field
from typing import Optional, List


# Dataklasse die één boek uit de Goodreads-export vertegenwoordigt.
# Wordt gebruikt als tussenformaat tussen de CSV en de graaf.
@dataclass
class BookNode:
    id: str               # Unieke sleutel: "Titel::Auteur"
    title: str
    author: str
    rating: Optional[int] = None  # Goodreads-beoordeling (1–5), of None als niet beoordeeld

    subjects: List[str] = field(default_factory=list)  # Onderwerpen opgehaald via OpenLibrary
    cover_url: Optional[str] = None       # URL naar omslagfoto
    openlibrary_id: Optional[str] = None  # OpenLibrary work-sleutel, bijv. /works/OL123W
    inventaire_uri: Optional[str] = None  # Inventaire/Wikidata URI, bijv. wd:Q43361
