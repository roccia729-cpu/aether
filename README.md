# Aether

Behavioral log analysis for Linux. Detects when a machine starts behaving differently.

## The problem
Logs are huge and mostly noise. Grep finds what you already know to look for; it misses what changed.

## What Aether does
- Builds a baseline of normal behavior from journald and /var/log
- Flags volume spikes, new messages, vanished messages, error bursts
- Prints a clean terminal report sorted by severity

## Status
v0.1 in development.
