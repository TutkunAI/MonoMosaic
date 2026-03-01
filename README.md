# MonoMosaic

An experimental graphics library sketch for HD44780 16x2 character displays, designed for making Graphics UI for character only displays, making them more cute

## Project Status

This is a work-in-progress testing sketch, not a finished library. It's used for experimentation and validation of ESP32's dual-core capabilities with display operations.

## Purpose

This project explores:
- Dual-Core Processing - Testing multi-core task distribution on ESP32
- HD44780 16x2 Display Control - Character display manipulation across cores
- Performance Analysis - Benchmarking core performance and synchronization
- Core Affinity - Testing task pinning and core communication

## Hardware

- ESP32 microcontroller (dual-core)
- HD44780 16x2 character display module

## Current Features

- Basic HD44780 16x2 display initialization
- Multi-core task creation and management
- Display refresh testing across CPU cores
- Core communication and synchronization primitives

## Usage

This is experimental code. Check the sketch files for current implementation details.

## Notes

- API and functionality are subject to change
- Not recommended for production use
- Use as a reference for ESP32 multi-core display projects

## Future Development

- [ ] Stabilize core task distribution
- [ ] Optimize inter-core communication
- [ ] Implement efficient display buffering
- [ ] Add comprehensive performance metrics
- [ ] Convert dis to production-ready library

## Author

TutkunAI - 2026

---

This is a testing/experimental project. Dont Crucify me!
