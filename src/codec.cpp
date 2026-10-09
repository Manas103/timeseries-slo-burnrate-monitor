// Delta-of-delta timestamp compression plus XOR float compression, the
// two techniques Facebook's Gorilla paper and this family of
// time-series engines (Monarch, Prometheus' TSDB) use: successive
// timestamps at a roughly fixed interval compress to a tiny delta-of-
// delta, and successive float values that change slowly compress by
// XORing with the previous value and encoding only the differing bits.
#include <cstdint>
#include <cstring>
#include <vector>
#include <random>
#include <chrono>
#include <iostream>
#include <cmath>

struct BitWriter {
    std::vector<uint8_t> bytes;
    uint8_t cur = 0;
    int nbits = 0;
    void putBit(int b) {
        cur = (cur << 1) | (b & 1);
        nbits++;
        if (nbits == 8) { bytes.push_back(cur); cur = 0; nbits = 0; }
    }
    void putBits(uint64_t v, int n) {
        for (int i = n - 1; i >= 0; i--) putBit((v >> i) & 1);
    }
    void flush() { if (nbits > 0) { cur <<= (8 - nbits); bytes.push_back(cur); cur = 0; nbits = 0; } }
    size_t sizeBytes() const { return bytes.size(); }
};

struct BitReader {
    const std::vector<uint8_t>& bytes;
    size_t bitPos = 0;
    explicit BitReader(const std::vector<uint8_t>& b) : bytes(b) {}
    int getBit() {
        size_t byteIdx = bitPos / 8;
        int bitIdx = 7 - (bitPos % 8);
        bitPos++;
        return (bytes[byteIdx] >> bitIdx) & 1;
    }
    uint64_t getBits(int n) {
        uint64_t v = 0;
        for (int i = 0; i < n; i++) v = (v << 1) | getBit();
        return v;
    }
};

static uint64_t zigzag(int64_t v) {
    return (uint64_t)((v << 1) ^ (v >> 63));
}
static int64_t unzigzag(uint64_t v) {
    return (int64_t)((v >> 1) ^ -(int64_t)(v & 1));
}

// Encodes a varint-like value using a small set of prefix-coded bucket
// widths, the same shape Gorilla uses for delta-of-delta: most deltas
// are tiny (a fixed scrape interval repeating), a few are not.
static void putVarBits(BitWriter& w, uint64_t zz) {
    if (zz == 0) { w.putBits(0, 1); return; }
    w.putBits(1, 1);
    int nbits = 64 - __builtin_clzll(zz);
    // unary length prefix (nbits-1 ones then a zero), then the bits themselves
    for (int i = 0; i < nbits - 1; i++) w.putBit(1);
    w.putBit(0);
    w.putBits(zz, nbits);
}
static uint64_t getVarBits(BitReader& r) {
    if (r.getBit() == 0) return 0;
    int nbits = 1;
    while (r.getBit() == 1) nbits++;
    return r.getBits(nbits);
}

class TimestampEncoder {
public:
    void encode(const std::vector<int64_t>& ts, BitWriter& w) {
        if (ts.empty()) return;
        w.putBits((uint64_t)ts[0], 64);
        int64_t prevDelta = 0;
        int64_t prevTs = ts[0];
        for (size_t i = 1; i < ts.size(); i++) {
            int64_t delta = ts[i] - prevTs;
            int64_t dod = delta - prevDelta;
            putVarBits(w, zigzag(dod));
            prevDelta = delta;
            prevTs = ts[i];
        }
    }
    std::vector<int64_t> decode(BitReader& r, size_t n) {
        std::vector<int64_t> out;
        if (n == 0) return out;
        int64_t first = (int64_t)r.getBits(64);
        out.push_back(first);
        int64_t prevDelta = 0, prevTs = first;
        for (size_t i = 1; i < n; i++) {
            int64_t dod = unzigzag(getVarBits(r));
            int64_t delta = prevDelta + dod;
            int64_t ts = prevTs + delta;
            out.push_back(ts);
            prevDelta = delta;
            prevTs = ts;
        }
        return out;
    }
};

class ValueEncoder {
public:
    void encode(const std::vector<double>& vals, BitWriter& w) {
        if (vals.empty()) return;
        uint64_t prevBits;
        std::memcpy(&prevBits, &vals[0], 8);
        w.putBits(prevBits, 64);
        int prevLeading = -1, prevTrailing = -1;
        for (size_t i = 1; i < vals.size(); i++) {
            uint64_t bits;
            std::memcpy(&bits, &vals[i], 8);
            uint64_t x = bits ^ prevBits;
            if (x == 0) {
                w.putBit(0);
            } else {
                w.putBit(1);
                int leading = __builtin_clzll(x);
                int trailing = __builtin_ctzll(x);
                if (prevLeading >= 0 && leading >= prevLeading && trailing >= prevTrailing) {
                    w.putBit(0);
                    int meaningful = 64 - prevLeading - prevTrailing;
                    w.putBits(x >> prevTrailing, meaningful);
                } else {
                    w.putBit(1);
                    w.putBits((uint64_t)leading, 6);
                    int meaningful = 64 - leading - trailing;
                    w.putBits((uint64_t)meaningful, 6);
                    w.putBits(x >> trailing, meaningful);
                    prevLeading = leading;
                    prevTrailing = trailing;
                }
            }
            prevBits = bits;
        }
    }
    std::vector<double> decode(BitReader& r, size_t n) {
        std::vector<double> out;
        if (n == 0) return out;
        uint64_t prevBits = r.getBits(64);
        double first;
        std::memcpy(&first, &prevBits, 8);
        out.push_back(first);
        int prevLeading = 0, prevTrailing = 0;
        for (size_t i = 1; i < n; i++) {
            if (r.getBit() == 0) {
                double v;
                std::memcpy(&v, &prevBits, 8);
                out.push_back(v);
                continue;
            }
            uint64_t x;
            if (r.getBit() == 0) {
                int meaningful = 64 - prevLeading - prevTrailing;
                uint64_t m = r.getBits(meaningful);
                x = m << prevTrailing;
            } else {
                int leading = (int)r.getBits(6);
                int meaningful = (int)r.getBits(6);
                uint64_t m = r.getBits(meaningful);
                int trailing = 64 - leading - meaningful;
                x = m << trailing;
                prevLeading = leading;
                prevTrailing = trailing;
            }
            uint64_t bits = prevBits ^ x;
            double v;
            std::memcpy(&v, &bits, 8);
            out.push_back(v);
            prevBits = bits;
        }
        return out;
    }
};

static bool selfCheck() {
    std::mt19937_64 rng(42);
    std::vector<int64_t> ts;
    std::vector<double> vals;
    int64_t t = 1700000000000;
    double v = 100.0;
    for (int i = 0; i < 100000; i++) {
        int jitterMs = (int)(rng() % 5) - 2;
        t += 1000 + jitterMs;
        ts.push_back(t);
        v += (double)((int)(rng() % 200) - 100) / 1000.0;
        vals.push_back(v);
    }
    BitWriter tw, vw;
    TimestampEncoder te;
    ValueEncoder ve;
    te.encode(ts, tw); tw.flush();
    ve.encode(vals, vw); vw.flush();
    BitReader tr(tw.bytes), vr(vw.bytes);
    auto ts2 = te.decode(tr, ts.size());
    auto vals2 = ve.decode(vr, vals.size());
    if (ts2 != ts) { std::cerr << "timestamp round trip mismatch\n"; return false; }
    for (size_t i = 0; i < vals.size(); i++) {
        if (vals2[i] != vals[i]) { std::cerr << "value round trip mismatch at " << i << "\n"; return false; }
    }
    double totalBytes = tw.sizeBytes() + vw.sizeBytes();
    double bytesPerSample = totalBytes / ts.size();
    std::cout << "self-check: " << ts.size() << " samples round-trip exact\n";
    std::cout << "compressed size: " << (long)totalBytes << " bytes (" << bytesPerSample << " bytes/sample, uncompressed would be 16)\n";
    return true;
}

static void throughputBenchmark() {
    const int N = 2000000;
    std::mt19937_64 rng(7);
    std::vector<int64_t> ts;
    std::vector<double> vals;
    ts.reserve(N); vals.reserve(N);
    int64_t t = 0;
    double v = 0;
    for (int i = 0; i < N; i++) {
        t += 1000;
        ts.push_back(t);
        v += (double)((int)(rng() % 20) - 10) / 1000.0;
        vals.push_back(v);
    }
    BitWriter tw, vw;
    TimestampEncoder te;
    ValueEncoder ve;
    auto start = std::chrono::steady_clock::now();
    te.encode(ts, tw); tw.flush();
    ve.encode(vals, vw); vw.flush();
    auto end = std::chrono::steady_clock::now();
    double secs = std::chrono::duration<double>(end - start).count();
    double samplesPerSec = N / secs;
    double bytesPerSample = (double)(tw.sizeBytes() + vw.sizeBytes()) / N;
    std::cout << "ingest benchmark: " << N << " samples in " << secs << "s = " << (long)samplesPerSec << " samples/sec, "
              << bytesPerSample << " bytes/sample\n";
}

int main() {
    bool ok = selfCheck();
    throughputBenchmark();
    return ok ? 0 : 1;
}
