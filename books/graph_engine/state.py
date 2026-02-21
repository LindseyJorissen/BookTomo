# Globale applicatiestatus — gedeeld tussen alle views binnen één serverproces.
# Let op: bij meerdere gelijktijdige gebruikers overschrijven ze elkaars data.
# Enkel voor persoonlijk gebruik!

BOOK_NODES = []  # Lijst van BookNode-objecten na het uploaden van de CSV
GRAPH = None     # NetworkX-graaf gebouwd vanuit BOOK_NODES
