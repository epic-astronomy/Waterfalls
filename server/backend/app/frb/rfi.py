"""
RFI masking and detrending of a dynamic spectrum, before dedispersion.

Follows the CHIME/FRB L1 chain (Rafiei-Ravandi & Smith 2023, ApJS 265, 62;
arXiv:2206.07292): a clipping chain of standard-deviation and intensity
clippers iterated six times, a detrending pass that only updates the mask, the
clipping chain six more times, and a final detrending of the intensity so the
dedispersion transform sees zero-mean data. Masked samples become NaN.

Adapted to EPIC pixel spectra: 64 channels instead of 1024, 83.6 ms samples
instead of 1 ms, and channels standardised first because the pixel units are
not calibrated and differ between channels. The time detrender works on chunks
much longer than the dispersion smearing, so it cannot remove a burst that is
smeared over tens of seconds in the low bands. Because these windows are
minutes long rather than CHIME's 4 s chunks, slow trends are removed once
before the first clipping chain.
"""

import numpy as np
from numpy.polynomial import legendre

N_ITER = 6
STDV_SIGMA = 3.0
INTENSITY_SIGMA = 5.0
INNER_ITER = 9
TIME_DEGREE = 4
FREQ_DEGREE = 4
MIN_CHUNK = 64


def _clipped_stats(x, mask, axis, inner_sigma):
    """Mean and std along an axis from the unmasked values, iteratively clipped"""
    m = mask.copy()
    for _ in range(INNER_ITER):
        w = m.astype(float)
        n = w.sum(axis=axis, keepdims=True)
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = np.where(n > 0, (np.where(m, x, 0.0)).sum(axis=axis, keepdims=True) / n, np.nan)
            var = np.where(n > 1, (np.where(m, (x - mean) ** 2, 0.0)).sum(axis=axis, keepdims=True) / n, np.nan)
        std = np.sqrt(var)
        new = mask & (np.abs(x - mean) <= inner_sigma * std)
        if np.array_equal(new, m):
            break
        m = new
    return mean, std


def _downsample(x, mask, dt, df):
    """Block-average by dt samples in time and df channels, with weights"""
    nt, nf = x.shape[0] // dt * dt, x.shape[1] // df * df
    w = mask[:nt, :nf].astype(float)
    xs = np.where(mask[:nt, :nf], x[:nt, :nf], 0.0)
    ws = w.reshape(nt // dt, dt, nf // df, df).sum(axis=(1, 3))
    s = xs.reshape(nt // dt, dt, nf // df, df).sum(axis=(1, 3))
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(ws > 0, s / ws, 0.0), ws > 0, (nt, nf)


def _upsample(bad, dt, df, shape, full_shape):
    out = np.zeros(full_shape, bool)
    out[: shape[0], : shape[1]] = np.repeat(np.repeat(bad, dt, axis=0), df, axis=1)
    return out


def _intensity_clip(x, mask, axis, inner_sigma, dt=1, df=1):
    """Mask samples more than INTENSITY_SIGMA from the mean along an axis
    (None for both), after downsampling by (dt, df)"""
    xd, md, shape = _downsample(x, mask, dt, df)
    mean, std = _clipped_stats(xd, md, axis, inner_sigma)
    bad = md & (np.abs(xd - mean) > INTENSITY_SIGMA * std)
    return mask & ~_upsample(bad, dt, df, shape, x.shape)


def _stdv_clip(x, mask, axis, block=256):
    """Mask rows whose spread along an axis is an outlier among all rows,
    judged with the median and MAD of the spreads. Along time (axis 0) each
    channel is judged per block of samples, as CHIME judges each 4 s chunk, so
    a short burst of RFI costs only its block. Along frequency (axis 1) whole
    samples are masked."""
    nt = x.shape[0]
    if axis == 0:
        starts = list(range(0, nt, block))
        if len(starts) > 1 and nt - starts[-1] < block // 2:
            starts.pop()  # fold a short tail into the previous block
        bounds = list(zip(starts, starts[1:] + [nt]))
        var = np.full((len(bounds), x.shape[1]), np.nan)
        for i, (a, b) in enumerate(bounds):
            m = mask[a:b]
            n = m.sum(axis=0)
            with np.errstate(invalid="ignore", divide="ignore"):
                mean = np.where(m, x[a:b], 0.0).sum(axis=0) / n
                var[i] = np.where(n > 8, np.where(m, (x[a:b] - mean) ** 2, 0.0).sum(axis=0) / n, np.nan)
    else:
        n = mask.sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = np.where(mask, x, 0.0).sum(axis=1) / n
            var = np.where(n > 8, np.where(mask, (x - mean[:, None]) ** 2, 0.0).sum(axis=1) / n, np.nan)
    ok = np.isfinite(var)
    if ok.sum() < 3:
        return mask
    med = np.median(var[ok])
    scale = 1.4826 * np.median(np.abs(var[ok] - med))
    bad = ~ok | (np.abs(var - med) > STDV_SIGMA * scale) if scale > 0 else ~ok
    out = mask.copy()
    if axis == 0:
        for i, (a, b) in enumerate(bounds):
            out[a:b, bad[i]] = False
    else:
        out[bad] = False
    return out


def _clipping_chain(x, mask):
    for _ in range(N_ITER):
        before = mask.sum()
        for axis in (0, 0, 0, 1, 1):
            mask = _stdv_clip(x, mask, axis)
        mask = _intensity_clip(x, mask, axis=1, inner_sigma=5.0)
        mask = _intensity_clip(x, mask, axis=0, inner_sigma=5.0)
        mask = _intensity_clip(x, mask, axis=None, inner_sigma=3.0, dt=16, df=2)
        mask = _intensity_clip(x, mask, axis=1, inner_sigma=3.0, dt=16, df=2)
        if mask.sum() == before:
            break
    return mask


def _fit(y, w, degree):
    """Weighted Legendre fit of y over its index, evaluated at every index"""
    n = len(y)
    if w.sum() <= degree + 1:
        return None
    u = np.linspace(-1, 1, n)
    v = legendre.legvander(u, degree)
    sw = np.sqrt(w)
    coef, *_ = np.linalg.lstsq(v * sw[:, None], y * sw, rcond=None)
    return v @ coef


def _detrend(x, mask, chunk):
    """Subtract a polynomial along time in chunks, then one along frequency.
    Rows or chunks whose fit fails are masked, as in CHIME/FRB."""
    x = x.copy()
    nt, nf = x.shape
    for c in range(nf):
        for t0 in range(0, nt, chunk):
            sl = slice(t0, min(nt, t0 + chunk))
            fit = _fit(np.where(mask[sl, c], x[sl, c], 0.0), mask[sl, c].astype(float), TIME_DEGREE)
            if fit is None:
                mask[sl, c] = False
            else:
                x[sl, c] -= fit
    # along frequency, every sample at once through the weighted normal equations
    v = legendre.legvander(np.linspace(-1, 1, nf), FREQ_DEGREE)
    w = mask.astype(float)
    y = np.where(mask, x, 0.0)
    gram = np.einsum("tf,fi,fj->tij", w, v, v)
    rhs = np.einsum("tf,fi,tf->ti", w, v, y)
    ok = w.sum(axis=1) > FREQ_DEGREE + 1
    coef = np.zeros((nt, FREQ_DEGREE + 1))
    if ok.any():
        # pinv rather than solve, in case a sample's unmasked channels leave the fit singular
        coef[ok] = (np.linalg.pinv(gram[ok]) @ rhs[ok][..., None])[..., 0]
    x -= coef @ v.T
    mask[~ok] = False
    return x, mask


def _restandardise(x, mask):
    """Scale each channel to unit robust spread over its unmasked samples"""
    v = np.where(mask, x, np.nan)
    med = np.nanmedian(v, axis=0)
    mad = 1.4826 * np.nanmedian(np.abs(v - med), axis=0)
    ok = np.isfinite(mad) & (mad > 0)
    return np.where(ok, (x - np.where(ok, med, 0.0)) / np.where(ok, mad, 1.0), x)


def clean(data: np.ndarray, dt: float, max_width_s: float) -> tuple[np.ndarray, np.ndarray]:
    """Standardise, mask and detrend a [n_time, n_chan] dynamic spectrum.
    Returns the cleaned data with masked samples as NaN, and the mask."""
    x = np.asarray(data, float)
    mask = np.isfinite(x)
    # static mask: channels with no data or no variation
    med = np.nanmedian(np.where(mask, x, np.nan), axis=0)
    mad = np.nanmedian(np.abs(np.where(mask, x, np.nan) - med), axis=0)
    dead = ~np.isfinite(mad) | (mad <= 0)
    mask[:, dead] = False
    with np.errstate(invalid="ignore", divide="ignore"):
        x = np.where(mask, (x - med) / (1.4826 * np.where(dead, 1.0, mad)), 0.0)

    chunk = max(MIN_CHUNK, int(np.ceil(8 * max_width_s / dt)))
    # CHIME clips 4 s chunks, over which drifts are negligible. These windows
    # last minutes, so remove slow trends first or the standard-deviation
    # clippers would mask drifting channels whole.
    x, _ = _detrend(x, mask.copy(), chunk)
    x = _restandardise(x, mask)
    mask = _clipping_chain(x, mask)
    _, mask = _detrend(x, mask, chunk)  # updates the mask only
    mask = _clipping_chain(x, mask)
    x, mask = _detrend(x, mask, chunk)

    # unit variance per channel over what is left
    with np.errstate(invalid="ignore", divide="ignore"):
        n = mask.sum(axis=0)
        sd = np.sqrt(np.where(mask, x**2, 0.0).sum(axis=0) / np.maximum(n, 1))
        x = np.where(mask & (sd > 0), x / np.where(sd > 0, sd, 1.0), np.nan)
    return x, mask
