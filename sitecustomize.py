"""Project interpreter customizations.

The former import hook patched live breadth calculations into the FastAPI
module. Market calculations now run only in the snapshot builder, so importing
the display service must have no side effects.
"""
