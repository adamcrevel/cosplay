"""Pluggable image-generation providers for the final costume edit.

`base.ImageProvider` is the seam: swap in a different provider by
implementing it, without touching `cli.py`, `vision.py`, or
`prompt_builder.py`. `pollinations.PollinationsProvider` is the one shipped
implementation.
"""
