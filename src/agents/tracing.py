"""Observability and tracing utilities for agent tools."""

from opentelemetry import trace

from src.utils.tracing import trace_tool

__all__ = ["trace", "trace_tool"]
