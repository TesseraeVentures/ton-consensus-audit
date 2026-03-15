# Pre-built TON Consensus Audit PoC
# Binary compiled from ton-blockchain/ton testnet branch @ commit 3bb6abc
# Build host: Ubuntu 24.04, Clang 18
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Runtime dependencies only (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    libatomic1 \
    libgsl27 \
    libgslcblas0 \
    libblas3 \
    libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /audit

# Place binary where PoC scripts expect it  
RUN mkdir -p /audit/ton/build-clang/test/consensus
COPY test-consensus /audit/ton/build-clang/test/consensus/test-consensus
RUN chmod +x /audit/ton/build-clang/test/consensus/test-consensus

# Copy PoC scripts
COPY poc/ /audit/poc/

# Copy reports for reference
COPY submissions/ /audit/submissions/
COPY README.md /audit/

# Verify binary works
RUN /audit/ton/build-clang/test/consensus/test-consensus --help | head -1

# Default: run the combined equivocation PoC (Finding 1 + 2)
ENTRYPOINT ["python3", "/audit/poc/test_equivocation_combined.py"]

# Alternative commands:
# docker run ton-consensus-audit python3 /audit/poc/test_equivocation.py
# docker run ton-consensus-audit python3 /audit/poc/test_twostep_amplification.py --check-source-only
