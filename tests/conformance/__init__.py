"""Conformance suite — SPEC-level invariants that any engram store must pass.

These tests verify the ``engram.conformance`` module against:

- a freshly-initialised store via ``engram init`` (happy path), and
- the v0.1 fixture under ``tests/fixtures/v0.1_store/`` before and after
  migration (regression path).

A third-party implementation (Rust port, Go port, Elixir port, …) that
points ``check_conformance`` at its store and sees zero failures is by
definition spec-compliant at the Layer-1 format level.
"""
