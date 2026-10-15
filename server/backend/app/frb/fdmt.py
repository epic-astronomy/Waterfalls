"""
Fast Dispersion Measure Transform (Zackay & Ofek 2017, ApJ 835, 11).

Sums a dynamic spectrum along every quadratic dispersion track with a total
delay of 0..max_delay samples across the band, by merging adjacent subbands
pairwise. The track sum is exact in the dispersion law and costs about
N_t * N_d * log2(N_f) operations, against N_t * N_d * N_f for brute force.
"""

import numpy as np


def fdmt(image: np.ndarray, f_edges: np.ndarray, max_delay: int) -> np.ndarray:
    """
    image: [n_chan, n_time] with channels in ascending frequency; n_chan must
        be a power of two. NaNs count as zero.
    f_edges: n_chan + 1 channel edges in MHz, ascending.
    max_delay: total delay in samples across the band for the largest DM.

    Returns [max_delay + 1, n_time]. Row d sums the track whose arrival at the
    bottom edge of the band is d samples after its arrival at the top edge,
    indexed by the arrival time at the bottom edge. The first d samples of row
    d are incomplete sums and are set to NaN.
    """
    n_chan, n_time = image.shape
    if n_chan & (n_chan - 1):
        raise ValueError("FDMT needs a power-of-two number of channels")
    data = np.nan_to_num(np.asarray(image, float))
    inv2 = np.asarray(f_edges, float) ** -2
    span = inv2[0] - inv2[-1]

    def n_delay(i0, i1):
        return int(np.ceil(max_delay * (inv2[i0] - inv2[i1]) / span))

    # initialisation: within a channel, the track spans d + 1 samples
    subbands = []
    for c in range(n_chan):
        nd = n_delay(c, c + 1)
        a = np.empty((nd + 1, n_time))
        a[0] = data[c]
        for d in range(1, nd + 1):
            a[d] = a[d - 1]
            a[d, d:] += data[c, :-d]
        subbands.append((c, c + 1, a))

    # merge pairs: the lower half is reached last, so its arrival time is the
    # subband's; the upper half is reached d_low samples earlier
    while len(subbands) > 1:
        merged = []
        for (lo0, lo1, a_lo), (up0, up1, a_up) in zip(subbands[0::2], subbands[1::2]):
            nd = n_delay(lo0, up1)
            a = np.zeros((nd + 1, n_time))
            frac = (inv2[lo0] - inv2[lo1]) / (inv2[lo0] - inv2[up1])
            for d in range(nd + 1):
                d_lo = min(int(round(d * frac)), a_lo.shape[0] - 1)
                d_up = min(d - d_lo, a_up.shape[0] - 1)
                a[d] = a_lo[d_lo]
                if d_lo:
                    a[d, d_lo:] += a_up[d_up, :-d_lo]
                else:
                    a[d] += a_up[d_up]
            merged.append((lo0, up1, a))
        subbands = merged

    out = subbands[0][2]
    for d in range(1, out.shape[0]):
        out[d, : min(d, n_time)] = np.nan
    return out
