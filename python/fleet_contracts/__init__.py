"""Shared page contracts the consumers run inside their own pytest suites.

Nothing here is imported by a running site. A consumer puts
`vendor/fleet-ui/python` on `sys.path` in its `tests/conftest.py` and calls a
contract against HTML its test client rendered, so the rule is written once and
judged against every consumer's real pages. Standard library only: fleet-ui has
no `pyproject.toml`, and a helper that needed one more dependency in four
consumers' lockfiles would be four chances for it to be missing.
"""
