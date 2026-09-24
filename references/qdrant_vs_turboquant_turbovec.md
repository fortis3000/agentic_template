# Research Evaluation: Qdrant vs TurboQuant & turbovec for Vector Microservice

**Ticket**: [#85](https://github.com/fortis3000/agentic_template/issues/85)  
**Parent Map**: [#79](https://github.com/fortis3000/agentic_template/issues/79)  
**Date**: September 2026  

---

## Executive Summary & Decision

For our containerized VectorDB MCP microservice, we evaluated three options:
1. **Option A: Use Qdrant as the primary persistent database.**
2. **Option B: Use turbovec as the primary vector engine.**
3. **Option C: Use a hybrid pattern (turbovec as an in-memory hot cache in front of Qdrant).**

**Final Decision: Adopt Option A — Qdrant as the Primary Vector Engine with Native TurboQuant / Turbo4 Configuration.**

### Key Finding
We do **not** have to choose between Qdrant and the TurboQuant algorithm. **Qdrant natively integrated Google Research's TurboQuant in version 1.18.0** (supporting 1-bit, 2-bit, and 4-bit quantization with rescoring) and introduced the **`turbo4` 4-bit storage datatype in Qdrant 1.19.0**. Our repository's `pyproject.toml` already specifies `qdrant-client>=1.18.0`.

`turbovec` (by Ryan Codrai) is a standalone Rust library implementing TurboQuant via an **exhaustive linear scan ($O(N)$)**. However, `turbovec` is **unsuitable** for our microservice due to critical architectural gaps:
1. **Lack of multimodal & sparse vectors**: It supports only single dense float32 vectors; it has zero native support for sparse vectors (SPLADE/BM25) or multiple named vectors (dense text + image), which are core requirements in our codebase (`src/tools/local/qdrant_db.py`).
2. **Lack of graph indexing ($O(N)$ linear scan)**: As vector count scales beyond 1M, linear scanning latency scales linearly, whereas Qdrant's filterable HNSW graph executes in $O(\log N)$.
3. **GIL Contention in Python**: `turbovec`'s PyO3 bindings currently do not release the Global Interpreter Lock (GIL) during SIMD searches and I/O snapshots, causing blocking stalls in async Python 3.13 microservices.
4. **No Write-Ahead Log (WAL) or Distributed Clustering**: Persistence in `turbovec` relies on whole-file snapshotting via atomic renames; it lacks point-in-time durability, transactional updates, and distributed replication.
5. **Option C Hybrid Caching is Premature/Redundant**: Qdrant already provides in-memory operation (`location=":memory:"`) and in-RAM quantized index pinning (`memory: "pinned"`), rendering a dual-tier `turbovec` cache redundant and introducing cache invalidation friction.

---

## 1. Algorithmic Differences: TurboQuant vs Qdrant SQ & PQ

### A. TurboQuant (Google Research, ICLR 2026)
*Source: Amir Zandieh, Majid Daliri, Majid Hadian, Vahab Mirrokni, "TurboQuant: Online Vector Quantization with Near-optimal Distortion Rate", arXiv:2504.19874.*

Traditional vector quantization methods face a fundamental dilemma:
- **Scalar Quantization (SQ)** quantizes coordinates independently, but suffers high distortion when coordinates are anisotropic or correlated (common in modern embedding models with dominant outlier dimensions).
- **Product Quantization (PQ)** models coordinate subspaces and clusters them via $k$-means into codebooks. However, PQ requires an **offline training phase** on thousands of representative vectors, is sensitive to distribution drift, and relies on table lookups (ADC) that cause memory latency stalls on modern SIMD hardware.

**How TurboQuant Solves This (Codebook-Oblivious / Data-Oblivious):**
1. **Random Orthogonal Rotation (Block-Hadamard Transform)**:
   - TurboQuant applies a randomized orthogonal rotation $R \in \mathcal{O}(d)$ to input vectors $x \in \mathbb{R}^d$: $\tilde{x} = Rx$.
   - In practice, to avoid $O(d^2)$ dense matrix multiplication, it uses a randomized Fast Walsh-Hadamard Transform (FWHT) or Block-Hadamard Transform with random diagonal sign flips ($R = H D / \sqrt{d}$), running in $O(d \log d)$ time.
   - **Concentration of Measure**: By the Berry-Esseen theorem and spherical symmetry, rotating any vector spreads its energy uniformly across all dimensions. Each coordinate $\tilde{x}_i$ follows an identical, universal marginal distribution:
     $$p(z) \propto (1 - z^2)^{\frac{d-3}{2}} \xrightarrow{d \to \infty} \mathcal{N}\left(0, \frac{1}{d}\right)$$
   - **Zero Codebook Training**: Because the distribution of rotated coordinates is mathematically fixed for *any* input vector regardless of data distribution, optimal Lloyd-Max scalar quantization thresholds can be precalculated **analytically offline once**. No dataset sampling or $k$-means training is needed.
2. **TurboQuant-MSE vs TurboQuant-Prod (Unbiased Inner Product)**:
   - **TurboQuant-MSE**: Quantizes rotated coordinates to $b$ bits ($b \in \{1, 2, 4\}$) using the analytical Lloyd-Max thresholds. Expected distortion is bounded within $\approx 2.7\times$ of the Shannon rate-distortion lower bound.
   - **TurboQuant-Prod**: Standard MSE quantizers introduce contraction bias in dot products. TurboQuant corrects this by quantizing the residual error vector $\Delta = x - \hat{x}$ using a 1-bit Quantized Johnson-Lindenstrauss (QJL) projection (random sign projection). The inner product is estimated as:
     $$\widehat{\langle x, q \rangle} = \langle \hat{x}, q \rangle + \langle \Delta_{\text{QJL}}, q \rangle$$
     This estimator is mathematically proven to be **strictly unbiased** with minimal variance.

### B. Qdrant's Quantization Suite
1. **Scalar Quantization (SQ8)**: Maps `float32` coordinates to `int8` (4x compression). Requires calibrating quantile bounds on a dataset segment.
2. **Product Quantization (PQ)**: Divides $d$-dimensional vectors into $m$ subvectors and trains 256 centroids per subvector via $k$-means.
3. **Binary Quantization (BQ)**: Projects vectors to 1 bit per coordinate based on sign ($\ge 0$ vs $< 0$), yielding 32x compression.
4. **Native TurboQuant & Turbo4 in Qdrant (v1.18+)**:
   - **Qdrant 1.18.0**: Introduced native TurboQuant quantization (`QuantizationConfig(turbo=TurboQuantQuantizationConfig(bits=BITS4))`).
   - **Qdrant 1.19.0**: Introduced the `turbo4` datatype, storing vectors directly as 4-bit values on disk (0.5 bytes per dimension, 8x storage reduction) without requiring full float32 duplicates.

---

## 2. Feature Matrix: turbovec vs Qdrant

| Feature | turbovec (RyanCodrai) | Qdrant (v1.18+) | Project Impact |
| :--- | :---: | :---: | :--- |
| **Multimodal Vectors (Text + Image)** | ❌ No | **✅ Yes** | Critical. `qdrant_db.py` uses named `dense` and `image` vectors. |
| **Sparse Vectors for Hybrid Search** | ❌ No | **✅ Yes** | Critical. `qdrant_db.py` supports bag-of-words sparse vectors with RRF fusion. |
| **Metadata Filtering** | ⚠️ Partial (ID lists) | **✅ Filterable HNSW** | Essential for scoping queries by user, document ID, and category. |
| **Persistence & Durability** | Snapshot file swap | **✅ Enterprise WAL** | Guarantees zero data loss on unexpected container restarts. |
| **Python 3.13 Concurrency** | ⚠️ GIL-bound FFI | **✅ Full Async** | Non-blocking async I/O in FastAPI/MCP. |

---

## 3. Implementation Recommendations

1. **Retain Qdrant** as the primary vector storage and search service in `docker-compose.yml`.
2. **Enable TurboQuant Quantization**: In collection configuration, specify 4-bit TurboQuant quantization for 8x RAM compression with minimal recall loss.
3. **Use Turbo4 Datatype for High-Density Collections**: For large document corpora in Qdrant 1.19+, store dense vectors directly in the `turbo4` format.

---

## Primary Sources
- Amir Zandieh et al., *"TurboQuant: Online Vector Quantization with Near-optimal Distortion Rate"*, arXiv:2504.19874, ICLR 2026.
- Ryan Codrai, *turbovec Repository*, [GitHub](https://github.com/RyanCodrai/turbovec).
- Qdrant Documentation, *"TurboQuant Quantization in Qdrant"*, [Qdrant Article](https://qdrant.tech/articles/turboquant-quantization/).

